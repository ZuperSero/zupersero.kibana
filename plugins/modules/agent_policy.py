# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later
# pylint: disable=unsupported-binary-operation

"""Manage one Kibana Fleet agent policy."""

DOCUMENTATION = r"""
---
module: agent_policy
short_description: Manage a Kibana Fleet agent policy
description:
  - Creates, updates, reads, and deletes one Fleet agent policy.
  - Omitted writable fields are preserved during updates.
  - Policies can be addressed by I(id), or by a unique exact I(name) in the selected space.
  - Supports check mode, diff mode, idempotency, and force deletion.
version_added: "1.0.0"
author:
  - Zupersero (@zupersero)
extends_documentation_fragment:
  - zupersero.kibana.kibana
options:
  id:
    description: Kibana-generated agent-policy identifier.
    type: str
  name:
    description: Policy display name; required when creating a policy.
    type: str
  description:
    description: Policy description. Omit it during an update to preserve the current value.
    type: str
  namespace:
    description: Fleet namespace. Defaults to C(default) when creating a policy if omitted.
    type: str
    default: default
  monitoring_enabled:
    description: Monitoring streams enabled for the policy.
    type: list
    elements: str
    choices: [logs, metrics, traces]
  data_output_id:
    description: Fleet output used for agent data.
    type: str
  monitoring_output_id:
    description: Fleet output used for monitoring data.
    type: str
  fleet_server_host_id:
    description: Fleet Server host associated with the policy.
    type: str
  download_source_id:
    description: Agent binary download source associated with the policy.
    type: str
  inactivity_timeout:
    description: Agent inactivity timeout in seconds.
    type: int
  unenroll_timeout:
    description: Agent unenrollment timeout in seconds.
    type: int
  keep_monitoring_alive:
    description: Keep monitoring enabled while disabling logs and metrics collection.
    type: bool
  global_data_tags:
    description: Data tags added to all inputs in this policy.
    type: list
    elements: dict
  overrides:
    description: Advanced policy setting overrides.
    type: dict
  required_versions:
    description: Agent versions and target percentages for automatic upgrades.
    type: list
    elements: dict
  agent_features:
    description: Agent feature enablement settings.
    type: list
    elements: dict
  force:
    description: Force deletion when the policy is still referenced by agents or policies.
    type: bool
    default: false
  sensitive_fields:
    description: Dot-separated response fields to redact from output and diffs.
    type: list
    elements: str
    default: []
  state:
    description: Whether the policy should exist.
    type: str
    choices: [present, absent]
    default: present
notes:
  - Fleet agent-policy privileges are required.
  - An explicit I(id) never creates a replacement when that policy is missing.
  - Deleting a policy can unenroll or detach agents when I(force=true); use it deliberately.
"""

EXAMPLES = r"""
- name: Create a Fleet policy
  zupersero.kibana.agent_policy:
    name: Application agents
    namespace: application
    description: Agents for application workloads
    monitoring_enabled: [logs, metrics]

- name: Update one field while preserving all other policy settings
  zupersero.kibana.agent_policy:
    id: application-policy
    description: Updated description

- name: Remove a policy that is still referenced
  zupersero.kibana.agent_policy:
    id: application-policy
    state: absent
    force: true
"""

RETURN = r"""
agent_policy:
  description: Current or resulting Fleet agent policy; null after deletion.
  returned: always
  type: dict
status:
  description: HTTP status code of the last API operation.
  returned: always
  type: int
diff:
  description: Sanitized before and after managed state.
  returned: when diff mode is enabled and a change is required
  type: dict
"""

from collections.abc import Mapping  # noqa: E402
from typing import Any  # noqa: E402

from ansible.module_utils.basic import AnsibleModule  # noqa: E402

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana  # noqa: E402


READ_SUCCESS_CODES = (200,)
CREATE_SUCCESS_CODES = (200, 201)
UPDATE_SUCCESS_CODES = (200,)
DELETE_SUCCESS_CODES = (200, 204)
NOT_FOUND_CODES = (404,)
MANAGED_FIELDS = (
    "name",
    "description",
    "namespace",
    "monitoring_enabled",
    "data_output_id",
    "monitoring_output_id",
    "fleet_server_host_id",
    "download_source_id",
    "inactivity_timeout",
    "unenroll_timeout",
    "keep_monitoring_alive",
    "global_data_tags",
    "overrides",
    "required_versions",
    "agent_features",
)


def agent_policy_argument_spec() -> dict[str, dict[str, Any]]:
    """Return the complete typed agent-policy argument specification."""
    argument_spec = kibana.kibana_argument_spec()
    argument_spec.update(
        id=dict(type="str"),
        name=dict(type="str"),
        description=dict(type="str"),
        namespace=dict(type="str", default="default"),
        monitoring_enabled=dict(
            type="list", elements="str", choices=["logs", "metrics", "traces"]
        ),
        data_output_id=dict(type="str"),
        monitoring_output_id=dict(type="str"),
        fleet_server_host_id=dict(type="str"),
        download_source_id=dict(type="str"),
        inactivity_timeout=dict(type="int"),
        unenroll_timeout=dict(type="int"),
        keep_monitoring_alive=dict(type="bool"),
        global_data_tags=dict(type="list", elements="dict"),
        overrides=dict(type="dict"),
        required_versions=dict(type="list", elements="dict"),
        agent_features=dict(type="list", elements="dict"),
        force=dict(type="bool", default=False),
        sensitive_fields=dict(type="list", elements="str", default=[]),
    )
    return argument_spec


def _unwrap(value: Any) -> Any:
    if isinstance(value, Mapping) and isinstance(value.get("item"), Mapping):
        return value["item"]
    return value


def _error(module: AnsibleModule, operation: str, status: int, response: Any) -> None:
    module.fail_json(
        msg=f"Kibana Fleet agent policy {operation} failed with HTTP {status}",
        status=status,
        response=kibana.sanitize(
            response,
            sensitive_fields=module.params.get("sensitive_fields", []),
        ),
    )


def _find_by_name(module: AnsibleModule, service: Any) -> tuple[int, dict | None]:
    status, response = service.list(full=False, per_page=100)
    if status not in READ_SUCCESS_CODES:
        _error(module, "lookup", status, response)
    items = response.get("items") if isinstance(response, Mapping) else None
    if not isinstance(items, list):
        module.fail_json(
            msg="Kibana Fleet agent-policy lookup returned a malformed response",
            status=status,
            response=kibana.sanitize(response),
        )
    matches = [item for item in items if isinstance(item, Mapping) and item.get("name") == module.params.get("name")]
    if len(matches) > 1:
        module.fail_json(
            msg=f"Multiple Fleet agent policies named `{module.params['name']}` exist; specify `id`"
        )
    return (status, dict(matches[0])) if matches else (404, None)


def _read(module: AnsibleModule, service: Any) -> tuple[int, dict | None]:
    if module.params.get("id"):
        status, response = service.get(module.params["id"])
        if status in READ_SUCCESS_CODES:
            value = _unwrap(response)
            return status, dict(value) if isinstance(value, Mapping) else None
        if status in NOT_FOUND_CODES:
            return status, None
        _error(module, "read", status, response)
    if not module.params.get("name"):
        module.fail_json(msg="One of `id` or `name` is required")
    return _find_by_name(module, service)


def _provided(
    module: AnsibleModule,
    current: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    params = module.params
    provided = {
        field: params[field]
        for field in MANAGED_FIELDS
        if field in params and params[field] is not None
    }
    # Ansible applies the creation default to updates as well. Preserve a
    # non-default server namespace when the caller omitted the option.
    if (
        current
        and current.get("namespace") not in (None, "default")
        and params.get("namespace") == "default"
    ):
        provided.pop("namespace", None)
    return provided


def _api_payload(current: Mapping[str, Any] | None, desired: Mapping[str, Any]) -> dict[str, Any]:
    payload = {}
    if current:
        payload.update({field: current[field] for field in MANAGED_FIELDS if field in current})
    payload.update(desired)
    return payload


def _safe_result(module: AnsibleModule, result: dict[str, Any]) -> None:
    fields = module.params.get("sensitive_fields", [])
    if "agent_policy" in result:
        result["agent_policy"] = kibana.sanitize(result["agent_policy"], fields)
    if "diff" in result:
        result["diff"] = kibana.sanitize(result["diff"], fields)
    module.exit_json(**result)


def run_module(module: AnsibleModule, client: kibana.KibanaClient | None = None) -> None:
    """Reconcile one Fleet agent policy."""
    client = client or kibana.KibanaClient(module)
    service = client.agent_policies
    status, current = _read(module, service)
    result: dict[str, Any] = {"changed": False, "agent_policy": current, "status": status}
    state = module.params["state"]

    if state == "absent":
        if current is None:
            _safe_result(module, result)
        result["changed"] = True
        if module._diff:
            result["diff"] = {"before": current, "after": {}}
        if module.check_mode:
            _safe_result(module, result)
        status, response = service.delete(module.params.get("id") or current["id"], force=module.params["force"])
        if status not in DELETE_SUCCESS_CODES:
            _error(module, "delete", status, response)
        result.update(status=status, agent_policy=None)
        _safe_result(module, result)

    provided = _provided(module, current)
    if current is None:
        if module.params.get("id"):
            module.fail_json(msg=f"Fleet agent policy `{module.params['id']}` does not exist; omit `id` to create by name")
        if not module.params.get("name"):
            module.fail_json(msg="Creating a Fleet agent policy requires `name`")
        payload = _api_payload(None, provided)
        preview = dict(payload)
        result.update(changed=True, agent_policy=preview)
        if module._diff:
            result["diff"] = {"before": {}, "after": preview}
        if module.check_mode:
            _safe_result(module, result)
        status, response = service.create(payload)
        if status not in CREATE_SUCCESS_CODES:
            _error(module, "create", status, response)
        result.update(status=status, agent_policy=_unwrap(response))
        _safe_result(module, result)

    desired = _api_payload(current, provided)
    changed, diff = kibana.comparison_diff(current, desired, sensitive_fields=module.params.get("sensitive_fields", []), unordered_lists=True)
    if not changed:
        _safe_result(module, result)
    result["changed"] = True
    if module._diff:
        result["diff"] = diff
    if module.check_mode:
        result["agent_policy"] = desired
        _safe_result(module, result)
    status, response = service.update(current["id"], desired)
    if status not in UPDATE_SUCCESS_CODES:
        _error(module, "update", status, response)
    result.update(status=status, agent_policy=_unwrap(response))
    _safe_result(module, result)


def main() -> None:
    module = AnsibleModule(
        argument_spec=agent_policy_argument_spec(),
        supports_check_mode=True,
        required_if=kibana.kibana_required_if(),
        required_together=kibana.kibana_required_together(),
        mutually_exclusive=kibana.kibana_mutually_exclusive(),
    )
    run_module(module)


if __name__ == "__main__":
    main()
