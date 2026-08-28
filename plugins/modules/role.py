# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later
# pylint: disable=unsupported-binary-operation

"""Manage a custom Kibana security role."""

DOCUMENTATION = r"""
---
module: role
short_description: Manage Kibana security roles
description:
  - Creates, updates, and deletes custom Kibana security roles.
  - Omitted top-level privilege sections are preserved during updates.
  - Supports check mode, diff mode, idempotency, and sanitized failures.
version_added: "1.0.0"
author:
  - Zupersero (@zupersero)
extends_documentation_fragment:
  - zupersero.kibana.kibana
options:
  name:
    description: Name of the Kibana role.
    type: str
    required: true
  description:
    description: Human-readable role description.
    type: str
  elasticsearch:
    description:
      - Elasticsearch privileges for the role.
      - The structure is passed to Kibana and remains compatible with version-specific privileges.
    type: dict
  kibana:
    description:
      - Kibana application privileges for the role.
      - Each item may contain C(base), C(feature), and C(spaces) values.
    type: list
    elements: dict
    suboptions:
      base:
        description: Base Kibana privileges.
        type: list
        elements: str
      feature:
        description: Feature privilege mapping.
        type: dict
      spaces:
        description: Kibana spaces to which the privilege applies.
        type: list
        elements: str
  metadata:
    description: Custom metadata associated with the role.
    type: dict
  transient_metadata:
    description:
      - Server-returned transient metadata associated with the role.
      - Kibana does not accept writes to this field; setting a different value fails safely.
    type: dict
  replace:
    description:
      - Treat omitted managed sections as empty values during an update.
      - Without this option, omitted sections retain their current values.
    type: bool
    default: false
  sensitive_fields:
    description: Dot-separated response and diff fields to redact.
    type: list
    elements: str
    default: []
  state:
    description: Whether the role should exist.
    type: str
    choices: [present, absent]
    default: present
notes:
  - Built-in and reserved roles are read-only and cannot be modified or deleted by this module.
  - Kibana validates privilege names and permissions on the server.
"""

EXAMPLES = r"""
- name: Manage an application role
  zupersero.kibana.role:
    name: observability-reader
    description: Read-only observability access
    elasticsearch:
      cluster: [monitor]
      indices:
        - names: ["logs-*"]
          privileges: [read, view_index_metadata]
          allow_restricted_indices: false
      run_as: []
    kibana:
      - base: [read]
        feature:
          dashboard: [read]
          discover: [read]
        spaces: [default]

- name: Clear omitted privilege sections deliberately
  zupersero.kibana.role:
    name: observability-reader
    elasticsearch: {}
    replace: true

- name: Delete a custom role
  zupersero.kibana.role:
    name: obsolete-role
    state: absent
"""

RETURN = r"""
role:
  description: Current or resulting role returned by Kibana.
  returned: always
  type: dict
status:
  description: HTTP status code of the last API operation.
  returned: always
  type: int
diff:
  description: Sanitized before and after managed role state.
  returned: when diff mode is enabled and a change is required
  type: dict
changed:
  description: Whether the role was created, updated, or deleted.
  returned: always
  type: bool
"""

from collections.abc import Mapping  # noqa: E402
from typing import Any  # noqa: E402

from ansible.module_utils.basic import AnsibleModule  # noqa: E402

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana  # noqa: E402


READ_SUCCESS_CODES = (200,)
WRITE_SUCCESS_CODES = (200, 201, 204)
DELETE_SUCCESS_CODES = (200, 204)
NOT_FOUND_CODES = (404,)
MANAGED_FIELDS = (
    "description",
    "elasticsearch",
    "kibana",
    "metadata",
)
REQUEST_FIELDS = (
    "description",
    "elasticsearch",
    "kibana",
    "metadata",
)
DEFAULTS = {
    "description": "",
    "elasticsearch": {},
    "kibana": [],
    "metadata": {},
    "transient_metadata": {},
}
RESPONSE_ONLY_FIELDS = frozenset(
    ("_reserved", "_transform_error", "_unrecognized_applications")
)


def role_argument_spec() -> dict[str, dict[str, Any]]:
    """Return the complete role argument specification."""
    argument_spec = kibana.kibana_argument_spec()
    argument_spec.update(
        name=dict(type="str", required=True),
        description=dict(type="str"),
        elasticsearch=dict(type="dict"),
        kibana=dict(
            type="list",
            elements="dict",
            options=dict(
                base=dict(type="list", elements="str"),
                feature=dict(type="dict"),
                spaces=dict(type="list", elements="str"),
            ),
        ),
        metadata=dict(type="dict"),
        transient_metadata=dict(type="dict"),
        replace=dict(type="bool", default=False),
        sensitive_fields=dict(type="list", elements="str", default=[]),
    )
    return argument_spec


def _managed(role: Mapping[str, Any]) -> dict[str, Any]:
    """Return only stable, module-managed role fields."""
    result = {
        field: role.get(field, DEFAULTS[field])
        for field in MANAGED_FIELDS
    }
    result["kibana"] = _normalize_kibana(result["kibana"])
    return result


def _normalize_kibana(value: Any) -> Any:
    """Normalize empty Kibana privilege maps added by the API."""
    if not isinstance(value, list):
        return value
    return [
        {**item, "feature": item.get("feature") or {}}
        if isinstance(item, Mapping)
        else item
        for item in value
    ]


def _normalize_elasticsearch(value: Any) -> Any:
    """Treat Kibana's expanded empty Elasticsearch privilege object as empty."""
    if not isinstance(value, Mapping):
        return value
    if set(value) <= {"cluster", "indices", "run_as"} and all(
        not item for item in value.values()
    ):
        return {}
    return value


def _desired(params: Mapping[str, Any]) -> dict[str, Any]:
    """Build managed desired state, preserving omitted sections by default."""
    desired = {
        field: params[field]
        for field in MANAGED_FIELDS
        if params.get(field) is not None
    }
    if params.get("replace"):
        for field in REQUEST_FIELDS:
            default = DEFAULTS[field]
            desired.setdefault(field, default)
    return desired


def _create_payload(params: Mapping[str, Any]) -> dict[str, Any]:
    """Build the complete payload required for role creation."""
    payload = {
        field: params.get(field, DEFAULTS[field])
        if params.get(field) is not None
        else DEFAULTS[field]
        for field in REQUEST_FIELDS
    }
    return _clean_nulls(payload)


def _clean_nulls(value: Any) -> Any:
    """Remove unset nested privilege options before sending to Kibana."""
    if isinstance(value, Mapping):
        return {key: _clean_nulls(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_clean_nulls(item) for item in value]
    return value


def _update_payload(current: Mapping[str, Any], desired: Mapping[str, Any]) -> dict[str, Any]:
    """Build a complete PUT body while preserving omitted sections."""
    payload = {
        field: current.get(field, DEFAULTS[field])
        for field in REQUEST_FIELDS
    }
    payload.update({field: value for field, value in desired.items() if field in REQUEST_FIELDS})
    return _clean_nulls(payload)


def _validate_transient_metadata(module: AnsibleModule, current: Any) -> None:
    """Reject attempts to write Kibana's server-managed transient metadata."""
    configured = module.params.get("transient_metadata")
    if configured is None:
        return
    if current is None or configured != current.get("transient_metadata", {}):
        module.fail_json(
            msg=(
                "`transient_metadata` is returned by Kibana but is server-managed "
                "and cannot be changed through the role API"
            )
        )


def _normalized_response(response: Any, role_name: str) -> dict[str, Any]:
    """Normalize Kibana role responses and remove diagnostic-only fields."""
    if isinstance(response, Mapping) and isinstance(response.get("role"), Mapping):
        response = response["role"]
    if not isinstance(response, Mapping):
        raise ValueError("response is not an object")
    result = {
        key: value for key, value in response.items() if key not in RESPONSE_ONLY_FIELDS
    }
    if "name" not in result or not isinstance(result.get("name"), str):
        raise ValueError("response did not contain a valid role name")
    for field, default in DEFAULTS.items():
        result.setdefault(field, default)
    return result


def _is_reserved(role: Mapping[str, Any]) -> bool:
    metadata = role.get("metadata")
    return bool(
        role.get("_reserved")
        or (isinstance(metadata, Mapping) and metadata.get("_reserved"))
    )


def _diff(
    current: Mapping[str, Any],
    desired: Mapping[str, Any],
    sensitive_fields: list[str],
) -> tuple[bool, dict[str, Any]]:
    before_value = {
        field: current.get(field, DEFAULTS[field]) for field in desired
    }
    after_value = dict(desired)
    if "kibana" in before_value:
        before_value["kibana"] = _normalize_kibana(before_value["kibana"])
        after_value["kibana"] = _normalize_kibana(after_value["kibana"])
    if "elasticsearch" in before_value:
        before_value["elasticsearch"] = _normalize_empty_maps(before_value["elasticsearch"])
        after_value["elasticsearch"] = _normalize_empty_maps(after_value["elasticsearch"])
    if "elasticsearch" in before_value:
        before_value["elasticsearch"] = _normalize_elasticsearch(
            before_value["elasticsearch"]
        )
        after_value["elasticsearch"] = _normalize_elasticsearch(
            after_value["elasticsearch"]
        )
    before = kibana.normalize_for_comparison(before_value)
    after = kibana.normalize_for_comparison(after_value)
    return before != after, {
        "before": kibana.sanitize(before, sensitive_fields=sensitive_fields),
        "after": kibana.sanitize(after, sensitive_fields=sensitive_fields),
    }


def _normalize_empty_maps(value: Any) -> Any:
    """Ignore server-materialized empty Elasticsearch privilege sections."""
    if isinstance(value, Mapping):
        return {
            key: _normalize_empty_maps(item)
            for key, item in value.items()
            if item not in (None, [], {})
        }
    if isinstance(value, list):
        return [_normalize_empty_maps(item) for item in value]
    return value


def _fail(
    module: AnsibleModule,
    operation: str,
    status: int,
    response: Any,
) -> None:
    module.fail_json(
        msg=(
            f"Kibana role {operation} failed for `{module.params['name']}` "
            f"with HTTP {status}"
        ),
        status=status,
        response=kibana.sanitize(
            response,
            sensitive_fields=module.params["sensitive_fields"],
        ),
    )


def _safe_result(module: AnsibleModule, result: dict[str, Any]) -> None:
    if "role" in result:
        result["role"] = kibana.sanitize(
            result["role"], sensitive_fields=module.params["sensitive_fields"]
        )
    if "diff" in result:
        result["diff"] = kibana.sanitize(
            result["diff"], sensitive_fields=module.params["sensitive_fields"]
        )
    module.exit_json(**result)


def _validated(
    module: AnsibleModule,
    operation: str,
    response: Any,
) -> dict[str, Any]:
    try:
        return _normalized_response(response, module.params["name"])
    except ValueError as error:
        module.fail_json(
            msg=(
                f"Kibana role {operation} returned a malformed response for "
                f"`{module.params['name']}`: {error}"
            ),
            response=kibana.sanitize(
                response,
                sensitive_fields=module.params["sensitive_fields"],
            ),
        )


def run_module(
    module: AnsibleModule,
    client: kibana.KibanaClient | None = None,
) -> None:
    """Reconcile one Kibana security role."""
    client = client or kibana.KibanaClient(module)
    service = client.roles
    role_name = module.params["name"]
    sensitive_fields = module.params["sensitive_fields"]
    status, response = service.get(role_name)
    if status in READ_SUCCESS_CODES:
        current = _validated(module, "read", response)
        raw_reserved = _is_reserved(response if isinstance(response, Mapping) else current)
    elif status in NOT_FOUND_CODES:
        current = None
        raw_reserved = False
    else:
        _fail(module, "read", status, response)

    result = {"changed": False, "role": current, "status": status}
    _validate_transient_metadata(module, current)
    if module.params["state"] == "absent":
        if current is None:
            _safe_result(module, result)
        if raw_reserved or _is_reserved(current):
            module.fail_json(
                msg=f"Kibana role `{role_name}` is reserved and cannot be deleted"
            )
        result["changed"] = True
        if getattr(module, "_diff", False):
            result["diff"] = {"before": current, "after": {}}
        if module.check_mode:
            _safe_result(module, result)
        status, response = service.delete(role_name)
        if status not in DELETE_SUCCESS_CODES:
            _fail(module, "delete", status, response)
        result.update(status=status, role=None)
        _safe_result(module, result)

    if current is None:
        payload = _create_payload(module.params)
        preview = {"name": role_name, **payload}
        result.update(changed=True, role=preview)
        if getattr(module, "_diff", False):
            result["diff"] = {"before": {}, "after": preview}
        if module.check_mode:
            _safe_result(module, result)
        status, response = service.create(role_name, payload)
        if status not in WRITE_SUCCESS_CODES:
            _fail(module, "create", status, response)
        if response is None:
            status, response = service.get(role_name)
            if status not in READ_SUCCESS_CODES:
                _fail(module, "read after create", status, response)
        result.update(status=status, role=_validated(module, "create", response))
        _safe_result(module, result)

    desired = _desired(module.params)
    changed, difference = _diff(current, desired, sensitive_fields)
    if not changed:
        _safe_result(module, result)
    if raw_reserved or _is_reserved(current):
        module.fail_json(
            msg=f"Kibana role `{role_name}` is reserved and cannot be modified"
        )
    result["changed"] = True
    if getattr(module, "_diff", False):
        result["diff"] = difference
    if module.check_mode:
        result["role"] = {**current, **desired}
        _safe_result(module, result)
    payload = _update_payload(current, desired)
    status, response = service.update(role_name, payload)
    if status not in WRITE_SUCCESS_CODES:
        _fail(module, "update", status, response)
    if response is None:
        status, response = service.get(role_name)
        if status not in READ_SUCCESS_CODES:
            _fail(module, "read after update", status, response)
    result.update(status=status, role=_validated(module, "update", response))
    _safe_result(module, result)


def main() -> None:
    module = AnsibleModule(
        argument_spec=role_argument_spec(),
        supports_check_mode=True,
        required_together=kibana.kibana_required_together(),
        mutually_exclusive=kibana.kibana_mutually_exclusive(),
    )
    run_module(module)


if __name__ == "__main__":
    main()
