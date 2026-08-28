# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared implementation for typed Kibana Fleet administration modules."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana


SUCCESS = range(200, 300)
NOT_FOUND = 404
REDACTION_FIELDS = ("secrets", "password", "service_token", "kibana_api_key")


def unwrap(response: Any) -> dict[str, Any] | None:
    """Extract a Fleet item from common API response envelopes."""
    if isinstance(response, Mapping):
        for key in ("item", "enrollment_api_key", "output", "proxy", "fleet_server_host"):
            item = response.get(key)
            if isinstance(item, Mapping):
                return dict(item)
        return dict(response)
    return None


def items(response: Any) -> list[dict[str, Any]]:
    if not isinstance(response, Mapping):
        return []
    for key in ("items", "list"):
        value = response.get(key)
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def _sanitize(module: AnsibleModule, value: Any) -> Any:
    return kibana.sanitize(
        value,
        sensitive_fields=module.params.get("sensitive_fields", []),
        secret_values=[
            module.params.get(field)
            for field in ("password", "output_password", "service_token", "kibana_api_key", "certificate_key")
        ],
    )


def _failure(module: AnsibleModule, operation: str, status: int, response: Any) -> None:
    module.fail_json(
        msg=f"Kibana Fleet {module.params['_resource']} {operation} failed with HTTP {status}",
        status=status,
        response=_sanitize(module, response),
    )


def _find(module: AnsibleModule, service: Any) -> dict[str, Any] | None:
    identifier = module.params.get("id")
    if identifier:
        status, response = service.get(identifier)
        if status in SUCCESS:
            return unwrap(response)
        if status == NOT_FOUND:
            return None
        _failure(module, "read", status, response)
    name = module.params.get("name")
    if not name:
        return None
    status, response = service.list()
    if status not in SUCCESS:
        _failure(module, "list", status, response)
    matches = [item for item in items(response) if item.get("name") == name]
    policy_id = module.params.get("policy_id")
    if policy_id:
        matches = [item for item in matches if item.get("policy_id") == policy_id]
    if len(matches) > 1:
        module.fail_json(msg=f"Multiple Fleet {module.params['_resource']} resources named `{name}` exist; specify `id`")
    return matches[0] if matches else None


def _desired(module: AnsibleModule, config: Mapping[str, Any]) -> dict[str, Any]:
    desired: dict[str, Any] = {}
    field_map = config.get("field_map", {})
    for field in config["fields"]:
        value = module.params.get(field)
        if value is not None:
            if field == "settings":
                desired.update(value)
            else:
                desired[field_map.get(field, field)] = value
    return desired


def argument_spec(config: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    spec = kibana.kibana_argument_spec()
    spec.update(
        id=dict(type="str"),
        name=dict(type="str"),
        sensitive_fields=dict(type="list", elements="str", default=[]),
        replace=dict(type="bool", default=False),
    )
    spec.update(config["spec"])
    return spec


def run_module(module: AnsibleModule, client: Any, config: Mapping[str, Any]) -> None:
    service = getattr(client, config["service"])
    module.params["_resource"] = config["resource"]
    current = _find(module, service)
    result: dict[str, Any] = {
        "changed": False,
        config["result"]: _sanitize(module, current),
        "status": 200,
    }
    desired = _desired(module, config)

    if module.params.get("state") == "absent":
        if current is None:
            module.exit_json(**result)
        result["changed"] = True
        if module._diff:
            result["diff"] = {"before": _sanitize(module, current), "after": {}}
        if module.check_mode:
            module.exit_json(**result)
        status, response = service.delete(module.params.get("id") or current.get("id"))
        if status not in SUCCESS:
            _failure(module, "delete", status, response)
        result.update(status=status, **{config["result"]: None})
        module.exit_json(**result)

    required = config.get("required", ())
    if current is None:
        missing = [field for field in required if not module.params.get(field)]
        if missing:
            module.fail_json(msg=f"Creating a Fleet {config['resource']} requires: " + ", ".join(f"`{field}`" for field in missing))
        payload = dict(desired)
        preview = dict(payload)
        result.update(changed=True, **{config["result"]: _sanitize(module, preview)}, status=0)
        if module._diff:
            result["diff"] = {"before": {}, "after": _sanitize(module, preview)}
        if module.check_mode:
            module.exit_json(**result)
        status, response = service.create(payload)
        if status not in SUCCESS:
            _failure(module, "create", status, response)
        result.update(status=status, **{config["result"]: _sanitize(module, unwrap(response))})
        module.exit_json(**result)

    projected = dict(current)
    projected.update(desired)
    ignored = ["is_preconfigured", "is_internal"]
    changed = kibana.normalize_for_comparison(
        projected, ignore_fields=ignored
    ) != kibana.normalize_for_comparison(current, ignore_fields=ignored)
    if not changed:
        module.exit_json(**result)
    result["changed"] = True
    if module._diff:
        result["diff"] = {"before": _sanitize(module, current), "after": _sanitize(module, projected)}
    if module.check_mode:
        result[config["result"]] = _sanitize(module, projected)
        module.exit_json(**result)
    status, response = service.update(current["id"], desired)
    if status not in SUCCESS:
        _failure(module, "update", status, response)
    result.update(status=status, **{config["result"]: _sanitize(module, unwrap(response))})
    module.exit_json(**result)
