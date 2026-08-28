# Copyright (c) 2025, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared connection, HTTP, and comparison helpers for Kibana modules."""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import socket
import ssl
import tempfile
import time
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

from ansible.module_utils.basic import env_fallback
from ansible.module_utils.urls import basic_auth_header, fetch_url, url_argument_spec


REDACTED = "VALUE_SPECIFIED_IN_NO_LOG_PARAMETER"
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "kbn-xsrf": "true",
}
DEFAULT_RETRY_STATUS_CODES = [408, 429, *range(500, 600)]
SAFE_METHODS = frozenset(("GET", "HEAD", "OPTIONS"))
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?:authorization|api[_-]?key|bearer|credential|encoded|password|"
    r"private[_-]?key|secret|token)",
    re.IGNORECASE,
)


class KibanaRetryableError(Exception):
    """An HTTP or transport failure that can be retried safely."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response = response


def kibana_argument_spec(include_state: bool = True) -> dict[str, dict[str, Any]]:
    """Return the common argument specification used by Kibana modules."""
    argument_spec = url_argument_spec()
    for name in ("force", "http_agent", "use_proxy", "use_gssapi"):
        argument_spec.pop(name, None)

    argument_spec.update(
        url=dict(type="str", fallback=(env_fallback, ["KIBANA_URL"])),
        urls=dict(
            type="list",
            elements="str",
            fallback=(env_fallback, ["KIBANA_URLS"]),
        ),
        username=dict(type="str", fallback=(env_fallback, ["KIBANA_USERNAME"])),
        password=dict(
            type="str",
            no_log=True,
            fallback=(env_fallback, ["KIBANA_PASSWORD"]),
        ),
        api_key=dict(
            type="str",
            no_log=True,
            fallback=(env_fallback, ["KIBANA_API_KEY"]),
        ),
        bearer_token=dict(
            type="str",
            no_log=True,
            fallback=(env_fallback, ["KIBANA_BEARER_TOKEN"]),
        ),
        headers=dict(
            type="dict",
            default={},
            no_log=True,
            fallback=(env_fallback, ["KIBANA_HEADERS"]),
        ),
        space=dict(
            type="str",
            default="default",
            fallback=(env_fallback, ["KIBANA_SPACE"]),
        ),
        validate_certs=dict(
            type="bool",
            default=True,
            fallback=(env_fallback, ["KIBANA_VALIDATE_CERTS"]),
        ),
        ca_path=dict(
            type="path",
            fallback=(env_fallback, ["KIBANA_CA_PATH"]),
        ),
        ca_data=dict(
            type="str",
            fallback=(env_fallback, ["KIBANA_CA_DATA"]),
        ),
        client_cert=dict(
            type="path",
            fallback=(env_fallback, ["KIBANA_CLIENT_CERT"]),
        ),
        client_key=dict(
            type="path",
            no_log=True,
            fallback=(env_fallback, ["KIBANA_CLIENT_KEY"]),
        ),
        certificate_fingerprint=dict(
            type="str",
            fallback=(env_fallback, ["KIBANA_CERTIFICATE_FINGERPRINT"]),
        ),
        timeout=dict(
            type="int",
            default=30,
            fallback=(env_fallback, ["KIBANA_TIMEOUT"]),
        ),
        retries=dict(
            type="int",
            default=3,
            fallback=(env_fallback, ["KIBANA_RETRIES"]),
        ),
        retry_pause=dict(
            type="float",
            default=1.0,
            fallback=(env_fallback, ["KIBANA_RETRY_PAUSE"]),
        ),
        retry_status_codes=dict(
            type="list",
            elements="int",
            default=DEFAULT_RETRY_STATUS_CODES,
        ),
        retry_mutating_requests=dict(
            type="bool",
            default=False,
            fallback=(env_fallback, ["KIBANA_RETRY_MUTATING_REQUESTS"]),
        ),
    )
    if include_state:
        argument_spec["state"] = dict(
            type="str", choices=["present", "absent"], default="present"
        )
    return argument_spec


def kibana_required_together() -> list[list[str]]:
    """Return common paired-option constraints."""
    return [["username", "password"], ["url_username", "url_password"]]


def kibana_required_if() -> list[list[str]]:
    """Return common conditional constraints."""
    return []


def kibana_mutually_exclusive() -> list[list[str]]:
    """Return common mutually exclusive option constraints."""
    return [
        ["url", "urls"],
        ["ca_path", "ca_data"],
        ["username", "api_key", "bearer_token", "url_username"],
        ["password", "api_key", "bearer_token", "url_password"],
    ]


def encode_query(parameters: Mapping[str, Any] | None) -> str:
    """Encode query parameters in a deterministic order."""
    if not parameters:
        return ""
    items: list[tuple[str, Any]] = []
    for key in sorted(parameters):
        value = parameters[key]
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            items.extend((key, item) for item in value)
        else:
            items.append((key, value))
    return urlencode(items, doseq=True)


def add_query(path: str, parameters: Mapping[str, Any] | None) -> str:
    """Add deterministically encoded query parameters to a path."""
    query = encode_query(parameters)
    if not query:
        return path
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{query}"


def validate_api_path(path: str) -> str:
    """Validate that a request target is a relative API path."""
    if not path or any(ord(character) < 32 for character in path):
        raise ValueError("Kibana API path must be a non-empty relative path")
    parsed = urlsplit(path)
    if (
        parsed.scheme
        or parsed.netloc
        or path.startswith(("//", "\\\\"))
        or "\\" in parsed.path
    ):
        raise ValueError(
            "Kibana API path must be relative; absolute and cross-origin paths are not allowed"
        )
    return path


def extract_value(value: Any, path: str | None, default: Any = None) -> Any:
    """Extract a dot-separated path from dictionaries and lists."""
    if not path:
        return value
    current = value
    for component in path.split("."):
        if isinstance(current, Mapping):
            if component not in current:
                return default
            current = current[component]
        elif isinstance(current, list) and component.isdigit():
            index = int(component)
            if index >= len(current):
                return default
            current = current[index]
        else:
            return default
    return current


def _remove_path(value: Any, path: str) -> None:
    components = path.split(".")
    current = value
    for component in components[:-1]:
        if isinstance(current, dict):
            current = current.get(component)
        elif isinstance(current, list) and component.isdigit():
            index = int(component)
            current = current[index] if index < len(current) else None
        else:
            return
    if isinstance(current, dict):
        current.pop(components[-1], None)
    elif isinstance(current, list) and components[-1].isdigit():
        index = int(components[-1])
        if index < len(current):
            current[index] = None


def _canonical_sort_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def normalize_for_comparison(
    value: Any,
    ignore_fields: Iterable[str] | None = None,
    unordered_lists: bool = False,
) -> Any:
    """Return a stable copy suitable for idempotency comparisons."""
    if isinstance(value, Mapping):
        normalized: Any = {
            key: normalize_for_comparison(item, None, unordered_lists)
            for key, item in sorted(value.items())
        }
    elif isinstance(value, list):
        normalized = [
            normalize_for_comparison(item, None, unordered_lists) for item in value
        ]
        if unordered_lists:
            normalized.sort(key=_canonical_sort_key)
    else:
        normalized = value

    for path in ignore_fields or []:
        _remove_path(normalized, path)
    return normalized


def project_desired(current: Any, desired: Any) -> Any:
    """Project a server response onto fields controlled by the desired payload."""
    if isinstance(desired, Mapping) and isinstance(current, Mapping):
        return {
            key: project_desired(current.get(key), item)
            for key, item in desired.items()
        }
    if isinstance(desired, list) and isinstance(current, list):
        return current
    return current


def select_fields(value: Any, fields: Iterable[str] | None) -> Any:
    """Select configured comparison paths from a value."""
    if not fields:
        return value
    return {field: extract_value(value, field) for field in fields}


def sanitize(
    value: Any,
    sensitive_fields: Iterable[str] | None = None,
    secret_values: Iterable[str | None] | None = None,
) -> Any:
    """Redact credential-like keys, configured paths, and known secret values."""
    secrets = [item for item in (secret_values or []) if item]

    def _sanitize(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {
                key: (
                    REDACTED
                    if _SENSITIVE_KEY_PATTERN.search(str(key))
                    else _sanitize(child)
                )
                for key, child in item.items()
            }
        if isinstance(item, list):
            return [_sanitize(child) for child in item]
        if isinstance(item, tuple):
            return tuple(_sanitize(child) for child in item)
        if isinstance(item, str):
            result = item
            for secret in secrets:
                result = result.replace(secret, REDACTED)
            return result
        return item

    result = _sanitize(value)
    for path in sensitive_fields or []:
        _redact_path(result, path.split("."))
    return result


def _redact_path(value: Any, components: list[str]) -> None:
    """Redact a configured dotted path, traversing lists when needed."""
    if not components:
        return
    component = components[0]
    remaining = components[1:]
    if isinstance(value, dict):
        if component not in value:
            for item in value.values():
                _redact_path(item, components)
            return
        if not remaining:
            value[component] = REDACTED
        else:
            _redact_path(value[component], remaining)
    elif isinstance(value, list):
        if component.isdigit():
            index = int(component)
            if index < len(value):
                if remaining:
                    _redact_path(value[index], remaining)
                else:
                    value[index] = REDACTED
        else:
            for item in value:
                _redact_path(item, components)


def comparison_diff(
    current: Any,
    desired: Any,
    compare_fields: Iterable[str] | None = None,
    ignore_fields: Iterable[str] | None = None,
    sensitive_fields: Iterable[str] | None = None,
    unordered_lists: bool = False,
) -> tuple[bool, dict[str, Any]]:
    """Compare current and desired state and build an Ansible-style safe diff."""
    projected = project_desired(current, desired)
    before = normalize_for_comparison(
        select_fields(projected, compare_fields),
        ignore_fields,
        unordered_lists,
    )
    after = normalize_for_comparison(
        select_fields(desired, compare_fields),
        ignore_fields,
        unordered_lists,
    )
    return before != after, {
        "before": sanitize(before, sensitive_fields),
        "after": sanitize(after, sensitive_fields),
    }


def version_tuple(version: str | None) -> tuple[int, ...]:
    """Convert an Elastic version string into a comparable integer tuple."""
    if not version:
        return ()
    result = []
    for component in version.split("."):
        digits = "".join(character for character in component if character.isdigit())
        if not digits:
            break
        result.append(int(digits))
    return tuple(result)


class KibanaClient:
    """HTTP client shared by Kibana, Fleet, and generic API modules."""

    def __init__(self, module: Any) -> None:
        from ansible_collections.zupersero.kibana.plugins.module_utils.kibana_services import (
            AgentPolicyService,
            AgentService,
            AlertingRuleService,
            ConnectorService,
            DataViewService,
            EPMService,
            AgentDownloadSourceService,
            EnrollmentTokenService,
            FleetOutputService,
            FleetProxyService,
            FleetServerHostService,
            MaintenanceWindowService,
            PackagePolicyService,
            RoleService,
            SavedObjectService,
            SpaceService,
        )

        self.module = module
        configured_urls = module.params.get("urls") or []
        configured_url = module.params.get("url")
        self.urls = [item.rstrip("/") for item in configured_urls if item]
        if configured_url:
            self.urls.insert(0, configured_url.rstrip("/"))
        self.urls = list(dict.fromkeys(self.urls))
        if not self.urls:
            module.fail_json(msg="Kibana URL is required through `url`, `urls`, or KIBANA_URL")

        self.url = self.urls[0]
        self.username = module.params.get("username")
        self.password = module.params.get("password")
        self.api_key = module.params.get("api_key")
        self.bearer_token = module.params.get("bearer_token")
        self.headers = module.params.get("headers") or {}
        self.validate_certs = module.params.get("validate_certs", True)
        self.ca_path = module.params.get("ca_path")
        self.ca_data = module.params.get("ca_data")
        self.certificate_fingerprint = module.params.get("certificate_fingerprint")
        self.timeout = module.params.get("timeout", 30)
        self.retries = max(0, int(module.params.get("retries", 3)))
        self.retry_pause = max(0.0, float(module.params.get("retry_pause", 1.0)))
        configured_retry_codes = module.params.get("retry_status_codes")
        self.retry_status_codes = set(
            DEFAULT_RETRY_STATUS_CODES
            if configured_retry_codes is None
            else configured_retry_codes
        )
        self.retry_mutating_requests = bool(
            module.params.get("retry_mutating_requests", False)
        )
        self.space_id = module.params.get("space", "default")
        self._active_endpoint_index = 0
        self._fingerprint_verified_endpoints: set[str] = set()
        self._temporary_ca_path: str | None = None
        self._version: str | None = None
        self._validate_configuration()

        self.spaces = SpaceService(self)
        self.epm = EPMService(self)
        self.agent_policies = AgentPolicyService(self)
        self.agents = AgentService(self)
        self.alerting_rules = AlertingRuleService(self)
        self.data_views = DataViewService(self)
        self.connectors = ConnectorService(self)
        self.roles = RoleService(self)
        self.saved_objects = SavedObjectService(self)
        self.maintenance_windows = MaintenanceWindowService(self)
        self.package_policies = PackagePolicyService(self)
        self.fleet_outputs = FleetOutputService(self)
        self.fleet_proxies = FleetProxyService(self)
        self.fleet_server_hosts = FleetServerHostService(self)
        self.agent_download_sources = AgentDownloadSourceService(self)
        self.enrollment_tokens = EnrollmentTokenService(self)

    @property
    def _secret_values(self) -> list[str | None]:
        return [
            self.password,
            self.api_key,
            self.bearer_token,
            self.module.params.get("url_password"),
            *[str(value) for value in self.headers.values()],
        ]

    def _get_ca_path(self) -> str | None:
        if self.ca_path or not self.ca_data:
            return self.ca_path
        if self._temporary_ca_path:
            return self._temporary_ca_path
        temporary = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix="kibana-ca-",
            suffix=".pem",
            dir=getattr(self.module, "tmpdir", None),
            delete=False,
        )
        with temporary:
            temporary.write(self.ca_data)
        os.chmod(temporary.name, 0o600)
        self._temporary_ca_path = temporary.name
        return temporary.name

    def _validate_configuration(self) -> None:
        for endpoint in self.urls:
            parsed = urlsplit(endpoint)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                self.module.fail_json(
                    msg="Each Kibana endpoint must be an absolute HTTP(S) URL"
                )
        if self.certificate_fingerprint:
            fingerprint = self.certificate_fingerprint.replace(":", "").lower()
            if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
                self.module.fail_json(
                    msg="`certificate_fingerprint` must be a SHA-256 fingerprint"
                )
            if any(urlsplit(endpoint).scheme != "https" for endpoint in self.urls):
                self.module.fail_json(
                    msg="`certificate_fingerprint` can only be used with HTTPS endpoints"
                )
            self.certificate_fingerprint = fingerprint

    def _request_headers(
        self, extra_headers: Mapping[str, Any] | None = None
    ) -> dict[str, str]:
        headers = dict(DEFAULT_HEADERS)
        headers.update({str(key): str(value) for key, value in self.headers.items()})
        headers.update(
            {str(key): str(value) for key, value in (extra_headers or {}).items()}
        )
        authorization_key = next(
            (key for key in headers if key.lower() == "authorization"),
            "Authorization",
        )
        if self.api_key:
            headers[authorization_key] = f"ApiKey {self.api_key}"
        elif self.bearer_token:
            headers[authorization_key] = f"Bearer {self.bearer_token}"
        elif self.username is not None and self.password is not None:
            basic_header = basic_auth_header(self.username, self.password)
            if isinstance(basic_header, bytes):
                basic_header = basic_header.decode("ascii")
            headers[authorization_key] = basic_header
        return headers

    def _preflight_fingerprint(self, endpoint: str) -> None:
        """Pin the TLS leaf certificate before any HTTP secrets are constructed."""
        if (
            not self.certificate_fingerprint
            or endpoint in self._fingerprint_verified_endpoints
        ):
            return
        parsed = urlsplit(endpoint)
        hostname = parsed.hostname
        if not hostname:
            raise KibanaRetryableError("Kibana HTTPS endpoint has no hostname")
        try:
            if self.validate_certs:
                context = ssl.create_default_context(cafile=self._get_ca_path())
            else:
                context = ssl._create_unverified_context()  # noqa: SLF001
            with socket.create_connection(
                (hostname, parsed.port or 443),
                timeout=self.timeout,
            ) as plain_socket:
                with context.wrap_socket(
                    plain_socket,
                    server_hostname=hostname,
                ) as tls_socket:
                    peer_certificate = tls_socket.getpeercert(binary_form=True)
        except (OSError, ssl.SSLError, ValueError) as error:
            raise KibanaRetryableError(
                f"TLS certificate fingerprint preflight failed: {error}"
            ) from error
        actual = hashlib.sha256(peer_certificate).hexdigest()
        if actual != self.certificate_fingerprint:
            raise KibanaRetryableError(
                "Kibana TLS certificate fingerprint does not match"
            )
        self._fingerprint_verified_endpoints.add(endpoint)

    @staticmethod
    def _decode_response(
        response: Any,
        info: Mapping[str, Any],
        deserialize_json: bool = True,
    ) -> Any:
        body = response.read() if response is not None else info.get("body")
        if not body:
            return None
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")
        if not deserialize_json:
            return body
        try:
            return json.loads(body)
        except (TypeError, ValueError):
            return body

    def _send_request_impl(
        self,
        endpoint: str,
        path: str,
        method: str = "GET",
        data: Any = None,
        extra_headers: Mapping[str, Any] | None = None,
        sensitive_fields: Iterable[str] | None = None,
        serialize_json: bool = True,
        deserialize_json: bool = True,
        sanitize_success_response: bool = True,
    ) -> tuple[int, Any]:
        self._preflight_fingerprint(endpoint)
        url = f"{endpoint}/{path.lstrip('/')}"
        headers = self._request_headers(extra_headers)
        body = (
            json.dumps(data)
            if data is not None and serialize_json
            else data
        )
        response, info = fetch_url(
            self.module,
            url,
            data=body,
            headers=headers,
            method=method,
            timeout=self.timeout,
            ca_path=self._get_ca_path(),
            use_netrc=False,
            unredirected_headers=[
                "Authorization",
                *[str(key) for key in self.headers],
                *[str(key) for key in (extra_headers or {})],
            ],
        )
        status = int(info.get("status", -1))
        response_data = self._decode_response(
            response,
            info,
            deserialize_json=deserialize_json if 200 <= status < 300 else True,
        )
        sanitized_response = sanitize(response_data, secret_values=self._secret_values)
        sanitized_error_response = sanitize(
            sanitized_response,
            sensitive_fields=sensitive_fields,
        )

        if 200 <= status < 300:
            return (
                status,
                sanitized_response
                if sanitize_success_response
                else response_data,
            )
        if status < 0 or status in self.retry_status_codes:
            message = sanitize(info.get("msg", "request failed"), secret_values=self._secret_values)
            raise KibanaRetryableError(
                f"HTTP {status}: {message}",
                status_code=status,
                response=sanitized_error_response,
            )
        if status == 404:
            return status, sanitized_response or {"status": status, "error": "Not found"}

        message = (
            extract_value(sanitized_error_response, "message")
            or extract_value(sanitized_error_response, "error.message")
            or info.get("msg")
            or "request failed"
        )
        return status, {
            "status": status,
            "error": sanitize(message, secret_values=self._secret_values),
            "response": sanitized_error_response,
        }

    def _send_request(
        self,
        path: str,
        method: str = "GET",
        data: Any = None,
        extra_headers: Mapping[str, Any] | None = None,
        sensitive_fields: Iterable[str] | None = None,
        serialize_json: bool = True,
        deserialize_json: bool = True,
        sanitize_success_response: bool = True,
    ) -> tuple[int, Any]:
        try:
            validate_api_path(path)
        except ValueError as error:
            self.module.fail_json(msg=str(error))
        method = method.upper()
        retry_allowed = method in SAFE_METHODS or self.retry_mutating_requests
        attempts = self.retries + 1 if retry_allowed else 1
        last_error = None
        for attempt in range(attempts):
            endpoint_index = (
                self._active_endpoint_index + attempt
            ) % len(self.urls)
            endpoint = self.urls[endpoint_index]
            try:
                result = self._send_request_impl(
                    endpoint,
                    path,
                    method,
                    data,
                    extra_headers,
                    sensitive_fields,
                    serialize_json,
                    deserialize_json,
                    sanitize_success_response,
                )
                self._active_endpoint_index = endpoint_index
                return result
            except KibanaRetryableError as error:
                last_error = error
                if attempt >= attempts - 1:
                    break
                delay_limit = min(60.0, self.retry_pause * (2**attempt))
                if delay_limit:
                    time.sleep(random.uniform(0, delay_limit))
        if last_error is None:
            self.module.fail_json(
                msg=f"Kibana {method} {path} failed without an error response"
            )
        self.module.fail_json(
            msg=f"Kibana {method} {path} failed after {attempts} attempts: {last_error}",
            status=last_error.status_code,
            response=sanitize(
                last_error.response,
                sensitive_fields=sensitive_fields,
                secret_values=self._secret_values,
            ),
        )

    def request(
        self,
        method: str,
        path: str,
        data: Any = None,
        headers: Mapping[str, Any] | None = None,
        query: Mapping[str, Any] | None = None,
        sensitive_fields: Iterable[str] | None = None,
        serialize_json: bool = True,
        deserialize_json: bool = True,
        sanitize_success_response: bool = True,
    ) -> tuple[int, Any]:
        """Send an arbitrary HTTP request."""
        try:
            validate_api_path(path)
        except ValueError as error:
            self.module.fail_json(msg=str(error))
        return self._send_request(
            add_query(path, query),
            method=method.upper(),
            data=data,
            extra_headers=headers,
            sensitive_fields=sensitive_fields,
            serialize_json=serialize_json,
            deserialize_json=deserialize_json,
            sanitize_success_response=sanitize_success_response,
        )

    def get(self, path: str, headers: dict | None = None) -> tuple[int, Any]:
        return self.request("GET", path, headers=headers)

    def post(
        self, path: str, data: Any = None, headers: dict | None = None
    ) -> tuple[int, Any]:
        return self.request("POST", path, data=data, headers=headers)

    def put(
        self, path: str, data: Any = None, headers: dict | None = None
    ) -> tuple[int, Any]:
        return self.request("PUT", path, data=data, headers=headers)

    def patch(
        self, path: str, data: Any = None, headers: dict | None = None
    ) -> tuple[int, Any]:
        return self.request("PATCH", path, data=data, headers=headers)

    def delete(self, path: str, headers: dict | None = None) -> tuple[int, Any]:
        return self.request("DELETE", path, headers=headers)

    def space_path(self, path: str, space_id: str | None = None) -> str:
        """Scope an API path to an explicit or configured Kibana space."""
        try:
            validate_api_path(path)
        except ValueError as error:
            self.module.fail_json(msg=str(error))
        selected_space = self.space_id if space_id is None else space_id
        if (
            not selected_space
            or selected_space == "default"
            or path.startswith("/s/")
        ):
            return path
        return f"/s/{quote(selected_space, safe='')}/{path.lstrip('/')}"

    def paginate(
        self,
        path: str,
        response_path: str,
        query: Mapping[str, Any] | None = None,
        page_parameter: str = "page",
        per_page_parameter: str = "per_page",
        page_size: int = 100,
        max_pages: int = 100,
        sensitive_fields: Iterable[str] | None = None,
    ) -> tuple[int, list[Any], Any]:
        """Collect items from conventional page/per_page Kibana responses."""
        if page_size < 1:
            self.module.fail_json(msg="Kibana pagination page_size must be greater than zero")
        if max_pages < 1:
            self.module.fail_json(msg="Kibana pagination max_pages must be greater than zero")
        items: list[Any] = []
        last_response: Any = None
        last_status = 200
        base_query = dict(query or {})
        for page in range(1, max_pages + 1):
            page_query = {
                **base_query,
                page_parameter: page,
                per_page_parameter: page_size,
            }
            last_status, last_response = self.request(
                "GET",
                path,
                query=page_query,
                sensitive_fields=sensitive_fields,
            )
            if not 200 <= last_status < 300:
                return last_status, items, last_response
            page_items = extract_value(last_response, response_path)
            if not isinstance(page_items, list):
                self.module.fail_json(
                    msg=(
                        f"Kibana pagination response path `{response_path}` "
                        f"did not contain a list on page {page}"
                    ),
                    status=last_status,
                    response=sanitize(
                        last_response,
                        sensitive_fields=sensitive_fields,
                        secret_values=self._secret_values,
                    ),
                )
            items.extend(page_items)
            total = extract_value(last_response, "total")
            if len(page_items) < page_size or (
                isinstance(total, int) and len(items) >= total
            ):
                break
            if page == max_pages:
                self.module.fail_json(
                    msg=(
                        f"Kibana pagination reached max_pages={max_pages} "
                        "before the result set was exhausted"
                    ),
                    status=last_status,
                    response=sanitize(
                        last_response,
                        sensitive_fields=sensitive_fields,
                        secret_values=self._secret_values,
                    ),
                )
        return last_status, items, last_response

    def bulk(
        self,
        requests: Iterable[Mapping[str, Any]],
        fail_fast: bool = True,
    ) -> list[dict[str, Any]]:
        """Execute a sequence of API requests with structured results."""
        results = []
        for item in requests:
            status, response = self.request(
                str(item.get("method", "POST")),
                str(item["path"]),
                data=item.get("body"),
                headers=item.get("headers"),
                query=item.get("query"),
            )
            result = {"status": status, "response": response}
            results.append(result)
            if fail_fast and not 200 <= status < 300:
                break
        return results

    def version(self, refresh: bool = False) -> str | None:
        """Return the Kibana version reported by the status API."""
        if self._version is None or refresh:
            status, response = self.get("/api/status")
            if 200 <= status < 300:
                self._version = (
                    extract_value(response, "version.number")
                    or extract_value(response, "version")
                )
        return self._version

    def supports_version(self, minimum_version: str) -> bool:
        """Return whether Kibana meets a minimum version."""
        return version_tuple(self.version()) >= version_tuple(minimum_version)

    def supports_feature(
        self,
        path: str | None = None,
        minimum_version: str | None = None,
    ) -> bool:
        """Detect a feature by minimum version and/or an API endpoint."""
        if minimum_version and not self.supports_version(minimum_version):
            return False
        if path:
            status, _response = self.request("HEAD", path)
            return status != 404
        return True
