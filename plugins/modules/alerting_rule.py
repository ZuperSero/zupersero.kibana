# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

"""Manage one Kibana alerting rule."""

from __future__ import annotations

DOCUMENTATION = r"""
---
module: alerting_rule
short_description: Manage a Kibana alerting rule
description:
  - Creates, reads, updates, enables, disables, and deletes a Kibana alerting rule.
  - Uses an explicit identifier and is scoped to the selected Kibana space.
  - Preserves omitted writable fields by default because Kibana's update API otherwise replaces fields such as actions and parameters with empty defaults.
  - Supports check mode, diff mode, idempotency, and sanitized failures.
version_added: "1.0.0"
author:
  - Zupersero (@zupersero)
extends_documentation_fragment:
  - zupersero.kibana.kibana
options:
  id:
    description: Unique identifier for the alerting rule.
    type: str
    required: true
  name:
    description:
      - Display name for the rule.
      - Required when creating a rule. Omit it during an update to preserve the current name.
    type: str
  rule_type_id:
    description:
      - Kibana rule type identifier, such as C(.index-threshold) or C(.es-query).
      - Required when creating a rule and immutable after creation.
    type: str
  consumer:
    description:
      - Kibana application that owns the rule, such as C(stackAlerts).
      - Required when creating a rule and immutable after creation.
    type: str
  enabled:
    description:
      - Whether Kibana schedules the rule for execution.
      - Omit during an update to preserve the current enabled state.
    type: bool
  schedule:
    description:
      - Rule check schedule.
      - Required when creating a rule. Omit it during an update to preserve the current schedule.
    type: dict
    suboptions:
      interval:
        description: Check interval using seconds, minutes, hours, or days, for example C(5m).
        type: str
        required: true
  params:
    description:
      - Rule-type-specific parameters.
      - Omit during an update to preserve current parameters; use an empty dictionary to clear them when the rule type permits it.
    type: dict
  actions:
    description:
      - Connector actions run by the rule.
      - Connector secrets belong in the connector resource and must not be embedded here.
      - Omit during an update to preserve current actions; use an empty list to clear them.
    type: list
    elements: dict
    suboptions:
      id:
        description: Identifier of the Kibana connector.
        type: str
        required: true
      group:
        description: Rule-type action group.
        type: str
      params:
        description: Connector-specific action parameters.
        type: dict
      frequency:
        description: Per-action notification frequency.
        type: dict
        suboptions:
          notify_when:
            description: Condition that controls repeated action execution.
            type: str
            choices: [onActionGroupChange, onActiveAlert, onThrottleInterval]
            required: true
          summary:
            description: Whether the action sends an alert summary.
            type: bool
            required: true
          throttle:
            description: Throttle interval, or C(null) when not throttled.
            type: str
      alerts_filter:
        description: Kibana alerts filter object for the action.
        type: dict
      use_alert_data_for_template:
        description: Whether alert data is used as the action template.
        type: bool
      uuid:
        description: Action UUID returned or accepted by Kibana.
        type: str
  tags:
    description:
      - Rule tags.
      - Omit during an update to preserve current tags; use an empty list to clear them.
    type: list
    elements: str
  replace:
    description:
      - Treat omitted I(params), I(actions), and I(tags) as empty values.
      - Other omitted writable fields remain preserved.
    type: bool
    default: false
  sensitive_fields:
    description:
      - Dot-separated response fields to redact from output, diffs, and failures.
      - Use paths such as C(params.private_value) or C(actions.params.message).
      - Credential-like keys are always redacted automatically.
    type: list
    elements: str
    default: []
  state:
    description: Whether the rule should exist.
    type: str
    choices: [present, absent]
    default: present
notes:
  - The rule type and consumer must be authorized in the selected space and enabled by the active Elastic subscription.
  - Action parameters can contain sensitive notification content. Configure I(sensitive_fields) when those fields must not be returned.
"""

EXAMPLES = r"""
- name: Create a disabled index-threshold rule without external connectors
  zupersero.kibana.alerting_rule:
    id: high-error-count
    name: High error count
    rule_type_id: .index-threshold
    consumer: stackAlerts
    enabled: false
    schedule:
      interval: 5m
    params:
      index: ["application-logs-*"]
      timeField: "@timestamp"
      aggType: count
      groupBy: all
      thresholdComparator: ">"
      threshold: [100]
      timeWindowSize: 5
      timeWindowUnit: m
    actions: []
    tags: [operations]

- name: Change only the schedule and enable the rule
  zupersero.kibana.alerting_rule:
    id: high-error-count
    enabled: true
    schedule:
      interval: 10m

- name: Clear all rule actions
  zupersero.kibana.alerting_rule:
    id: high-error-count
    actions: []

- name: Delete the rule
  zupersero.kibana.alerting_rule:
    id: high-error-count
    state: absent
"""

RETURN = r"""
rule:
  description:
    - Current or resulting alerting rule returned by Kibana.
    - C(null) after deletion or when the requested absent rule does not exist.
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

import re  # noqa: E402
from collections.abc import Mapping  # noqa: E402
from typing import Any  # noqa: E402

from ansible.module_utils.basic import AnsibleModule  # noqa: E402

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana  # noqa: E402


READ_SUCCESS_CODES = (200,)
CREATE_SUCCESS_CODES = (200, 201)
UPDATE_SUCCESS_CODES = (200,)
ENABLED_SUCCESS_CODES = (200, 204)
DELETE_SUCCESS_CODES = (200, 204)
NOT_FOUND_CODES = (404,)
INTERVAL_PATTERN = re.compile(r"^[1-9][0-9]*[smhd]$")
WRITABLE_FIELDS = (
    "name",
    "schedule",
    "params",
    "actions",
    "tags",
    "notify_when",
    "throttle",
    "alert_delay",
    "artifacts",
    "flapping",
)
MANAGED_FIELDS = ("name", "schedule", "params", "actions", "tags")
REPLACE_DEFAULTS = {"params": {}, "actions": [], "tags": []}
ACTION_REQUEST_FIELDS = frozenset(
    (
        "alerts_filter",
        "frequency",
        "group",
        "id",
        "params",
        "use_alert_data_for_template",
        "uuid",
    )
)


def alerting_rule_argument_spec() -> dict[str, dict[str, Any]]:
    """Return the complete typed alerting-rule argument specification."""
    argument_spec = kibana.kibana_argument_spec()
    argument_spec.update(
        id=dict(type="str", required=True),
        name=dict(type="str"),
        rule_type_id=dict(type="str"),
        consumer=dict(type="str"),
        enabled=dict(type="bool"),
        schedule=dict(
            type="dict",
            options=dict(interval=dict(type="str", required=True)),
        ),
        params=dict(type="dict", no_log=True),
        actions=dict(
            type="list",
            elements="dict",
            no_log=True,
            options=dict(
                id=dict(type="str", required=True),
                group=dict(type="str"),
                params=dict(type="dict", no_log=True),
                frequency=dict(
                    type="dict",
                    options=dict(
                        notify_when=dict(
                            type="str",
                            required=True,
                            choices=[
                                "onActionGroupChange",
                                "onActiveAlert",
                                "onThrottleInterval",
                            ],
                        ),
                        summary=dict(type="bool", required=True),
                        throttle=dict(type="str"),
                    ),
                ),
                alerts_filter=dict(type="dict"),
                use_alert_data_for_template=dict(type="bool"),
                uuid=dict(type="str"),
            ),
        ),
        tags=dict(type="list", elements="str"),
        replace=dict(type="bool", default=False),
        sensitive_fields=dict(type="list", elements="str", default=[]),
    )
    return argument_spec


def _validate_params(module: AnsibleModule) -> None:
    if module.params["state"] != "present":
        return
    schedule = module.params.get("schedule")
    if schedule and not INTERVAL_PATTERN.fullmatch(schedule["interval"]):
        module.fail_json(
            msg=(
                "`schedule.interval` must be a positive integer followed by "
                "`s`, `m`, `h`, or `d`"
            )
        )


def _desired_definition(params: Mapping[str, Any]) -> dict[str, Any]:
    desired = {
        field: params[field]
        for field in MANAGED_FIELDS
        if params.get(field) is not None
    }
    if params.get("replace"):
        for field, default in REPLACE_DEFAULTS.items():
            desired.setdefault(field, default)
    return desired


def _create_payload(params: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "name": params["name"],
        "rule_type_id": params["rule_type_id"],
        "consumer": params["consumer"],
        "schedule": params["schedule"],
        "params": params.get("params") or {},
        "actions": params.get("actions") or [],
        "tags": params.get("tags") or [],
    }
    if params.get("enabled") is not None:
        payload["enabled"] = params["enabled"]
    return payload


def _update_payload(
    current: Mapping[str, Any],
    desired: Mapping[str, Any],
) -> dict[str, Any]:
    """Preserve fields Kibana's PUT endpoint would otherwise default or clear."""
    payload = {
        field: current[field]
        for field in WRITABLE_FIELDS
        if field in current
    }
    if isinstance(payload.get("actions"), list):
        payload["actions"] = _request_actions(payload["actions"])
    payload.update(desired)
    if isinstance(payload.get("actions"), list):
        payload["actions"] = _request_actions(payload["actions"])
    if (
        isinstance(desired.get("params"), Mapping)
        and desired["params"]
        and isinstance(current.get("params"), Mapping)
    ):
        payload["params"] = _merge_preview(current["params"], desired["params"])
    payload.setdefault("params", {})
    payload.setdefault("actions", [])
    payload.setdefault("tags", [])
    return payload


def _request_actions(actions: list[Any]) -> list[Any]:
    """Remove fields that Kibana returns but rejects in rule request bodies."""
    return [
        {
            key: value
            for key, value in action.items()
            if key in ACTION_REQUEST_FIELDS
        }
        if isinstance(action, Mapping)
        else action
        for action in actions
    ]


def _merge_preview(current: Any, desired: Any) -> Any:
    if isinstance(current, Mapping) and isinstance(desired, Mapping):
        if not desired:
            return {}
        result = dict(current)
        for key, value in desired.items():
            result[key] = _merge_preview(current.get(key), value)
        return result
    return desired


def _comparison_diff(
    current: Mapping[str, Any],
    desired: Mapping[str, Any],
    sensitive_fields: list[str],
) -> tuple[bool, dict[str, Any]]:
    comparable_current = dict(current)
    comparable_desired = dict(desired)
    if isinstance(comparable_current.get("actions"), list):
        comparable_current["actions"] = _request_actions(
            comparable_current["actions"]
        )
    if isinstance(comparable_desired.get("actions"), list):
        comparable_desired["actions"] = _request_actions(
            comparable_desired["actions"]
        )
    projected = kibana.project_desired(comparable_current, comparable_desired)
    for field, value in comparable_desired.items():
        if value == {} or value == []:
            projected[field] = comparable_current.get(field)
    before = kibana.normalize_for_comparison(projected)
    after = kibana.normalize_for_comparison(comparable_desired)
    return before != after, {
        "before": kibana.sanitize(before, sensitive_fields=sensitive_fields),
        "after": kibana.sanitize(after, sensitive_fields=sensitive_fields),
    }


def _sanitize_result(module: AnsibleModule, result: dict[str, Any]) -> None:
    sensitive_fields = module.params["sensitive_fields"]
    if "rule" in result:
        result["rule"] = kibana.sanitize(
            result["rule"],
            sensitive_fields=sensitive_fields,
        )
    if "diff" in result:
        result["diff"] = kibana.sanitize(
            result["diff"],
            sensitive_fields=sensitive_fields,
        )
    module.exit_json(**result)


def _fail_operation(
    module: AnsibleModule,
    operation: str,
    status: int,
    response: Any,
) -> None:
    module.fail_json(
        msg=(
            f"Kibana alerting rule {operation} failed for "
            f"{module.params['id']} with HTTP {status}"
        ),
        status=status,
        response=kibana.sanitize(
            response,
            sensitive_fields=module.params["sensitive_fields"],
        ),
    )


def _validated_rule(
    module: AnsibleModule,
    operation: str,
    status: int,
    response: Any,
) -> dict[str, Any]:
    if (
        not isinstance(response, Mapping)
        or not isinstance(response.get("id"), str)
        or not isinstance(response.get("name"), str)
        or not isinstance(response.get("rule_type_id"), str)
        or not isinstance(response.get("consumer"), str)
        or not isinstance(response.get("schedule"), Mapping)
        or not isinstance(response.get("actions"), list)
        or not isinstance(response.get("params"), Mapping)
        or not isinstance(response.get("enabled"), bool)
    ):
        module.fail_json(
            msg=(
                f"Kibana alerting rule {operation} returned a malformed "
                f"response for {module.params['id']}"
            ),
            status=status,
            response=kibana.sanitize(
                response,
                sensitive_fields=module.params["sensitive_fields"],
            ),
        )
    return dict(response)


def _validate_create_options(module: AnsibleModule) -> None:
    missing = [
        name
        for name in ("name", "rule_type_id", "consumer", "schedule")
        if module.params.get(name) is None
    ]
    if missing:
        module.fail_json(
            msg=(
                "Creating a Kibana alerting rule requires: "
                + ", ".join(f"`{name}`" for name in missing)
            )
        )


def _validate_immutable_options(
    module: AnsibleModule,
    current: Mapping[str, Any],
) -> None:
    for field in ("rule_type_id", "consumer"):
        desired = module.params.get(field)
        if desired is not None and desired != current.get(field):
            module.fail_json(
                msg=(
                    f"`{field}` is immutable for an existing Kibana alerting "
                    "rule; delete and recreate the rule to change it"
                )
            )


def run_module(
    module: AnsibleModule,
    client: kibana.KibanaClient | None = None,
) -> None:
    """Reconcile one typed Kibana alerting rule."""
    _validate_params(module)
    client = client or kibana.KibanaClient(module)
    service = client.alerting_rules
    rule_id = module.params["id"]
    sensitive_fields = module.params["sensitive_fields"]

    status, response = service.get(rule_id, sensitive_fields=sensitive_fields)
    if status in READ_SUCCESS_CODES:
        current = _validated_rule(module, "read", status, response)
    elif status in NOT_FOUND_CODES:
        current = None
    else:
        _fail_operation(module, "read", status, response)

    result = {"changed": False, "rule": current, "status": status}

    if module.params["state"] == "absent":
        if current is None:
            _sanitize_result(module, result)
        result["changed"] = True
        if module._diff:
            result["diff"] = {"before": current, "after": {}}
        if module.check_mode:
            _sanitize_result(module, result)
        status, response = service.delete(
            rule_id,
            sensitive_fields=sensitive_fields,
        )
        if status not in DELETE_SUCCESS_CODES:
            _fail_operation(module, "delete", status, response)
        result.update(status=status, rule=None)
        _sanitize_result(module, result)

    if current is None:
        _validate_create_options(module)
        payload = _create_payload(module.params)
        preview = {"id": rule_id, **payload}
        preview.setdefault("enabled", True)
        result.update(changed=True, rule=preview)
        if module._diff:
            result["diff"] = {"before": {}, "after": preview}
        if module.check_mode:
            _sanitize_result(module, result)
        status, response = service.create(
            rule_id,
            payload,
            sensitive_fields=sensitive_fields,
        )
        if status not in CREATE_SUCCESS_CODES:
            _fail_operation(module, "create", status, response)
        result.update(
            status=status,
            rule=_validated_rule(module, "create", status, response),
        )
        _sanitize_result(module, result)

    _validate_immutable_options(module, current)
    desired = _desired_definition(module.params)
    definition_changed, definition_diff = _comparison_diff(
        current,
        desired,
        sensitive_fields,
    )
    enabled = module.params.get("enabled")
    enabled_changed = enabled is not None and enabled != current.get("enabled")
    if not definition_changed and not enabled_changed:
        _sanitize_result(module, result)

    managed_desired = dict(desired)
    if enabled is not None:
        managed_desired["enabled"] = enabled
    diff = _comparison_diff(
        current,
        managed_desired,
        sensitive_fields,
    )[1]
    result["changed"] = True
    if module._diff:
        result["diff"] = diff if enabled_changed else definition_diff
    if module.check_mode:
        result["rule"] = _merge_preview(current, managed_desired)
        _sanitize_result(module, result)

    resulting_rule = current
    if definition_changed:
        payload = _update_payload(current, desired)
        status, response = service.update(
            rule_id,
            payload,
            sensitive_fields=sensitive_fields,
        )
        if status not in UPDATE_SUCCESS_CODES:
            _fail_operation(module, "update", status, response)
        resulting_rule = _validated_rule(module, "update", status, response)

    if enabled_changed:
        status, response = service.set_enabled(
            rule_id,
            enabled,
            sensitive_fields=sensitive_fields,
        )
        if status not in ENABLED_SUCCESS_CODES:
            _fail_operation(
                module,
                "enable" if enabled else "disable",
                status,
                response,
            )
        status, response = service.get(
            rule_id,
            sensitive_fields=sensitive_fields,
        )
        if status not in READ_SUCCESS_CODES:
            _fail_operation(module, "read after enabled-state change", status, response)
        resulting_rule = _validated_rule(
            module,
            "read after enabled-state change",
            status,
            response,
        )

    result.update(status=status, rule=resulting_rule)
    _sanitize_result(module, result)


def main() -> None:
    module = AnsibleModule(
        argument_spec=alerting_rule_argument_spec(),
        supports_check_mode=True,
        required_together=kibana.kibana_required_together(),
        mutually_exclusive=kibana.kibana_mutually_exclusive(),
    )
    run_module(module)


if __name__ == "__main__":
    main()
