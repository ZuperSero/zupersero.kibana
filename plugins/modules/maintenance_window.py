# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

"""Manage one Kibana maintenance window."""

from __future__ import annotations

DOCUMENTATION = r"""
---
module: maintenance_window
short_description: Manage a Kibana maintenance window
description:
  - Creates, finds, reads, partially updates, archives, and deletes a Kibana maintenance window.
  - Uses I(id) when supplied, otherwise an exact I(name) match provides stateless Ansible identity.
  - Supports one-time and recurring schedules, alert KQL scope, enabled state, check mode, diff mode, and idempotency.
version_added: "1.0.0"
author:
  - Zupersero (@zupersero)
extends_documentation_fragment:
  - zupersero.kibana.kibana
options:
  id:
    description:
      - Server-generated maintenance-window identifier.
      - For I(state=present), an explicit identifier can manage only an existing window; a missing identifier fails without creating a replacement.
      - Omit it to create or find a window through an exact, unique I(name) in the selected space.
    type: str
  name:
    description:
      - Maintenance-window title.
      - Required when creating a window.
    type: str
    aliases: [title]
  enabled:
    description:
      - Whether the window suppresses notifications while its schedule is active.
      - Omit during an update to preserve the current value.
    type: bool
  schedule:
    description:
      - Complete custom schedule.
      - Required when creating a window.
      - Supplying a schedule replaces the complete current schedule; omit I(recurring) to clear recurrence.
    type: dict
    suboptions:
      start:
        description: UTC ISO 8601 start timestamp.
        type: str
        required: true
      duration:
        description: Positive duration using C(d), C(h), C(m), or C(s), for example C(2h).
        type: str
        required: true
      timezone:
        description: Timezone used for recurrence, for example C(Europe/Copenhagen).
        type: str
      recurring:
        description: Recurrence configuration.
        type: dict
        suboptions:
          every:
            description: Positive recurrence interval using C(d), C(w), C(M), or C(y), for example C(2w).
            type: str
            required: true
          end:
            description: Optional UTC ISO 8601 recurrence end timestamp.
            type: str
          occurrences:
            description: Optional positive maximum number of occurrences.
            type: int
          on_week_day:
            description:
              - Weekdays such as C(MO) and C(FR), or an nth weekday such as C(+2TU) or C(-1FR).
            type: list
            elements: str
          on_month_day:
            description: Days of the month from 1 through 31.
            type: list
            elements: int
          on_month:
            description: Months from 1 through 12.
            type: list
            elements: int
  scope:
    description:
      - Optional alert filter.
      - Omit it during updates to preserve the current scope.
      - Use C(*) as the KQL value to explicitly match alerts from all supported rule categories.
    type: dict
    suboptions:
      alerting:
        description: Alerting scope definition.
        type: dict
        required: true
        suboptions:
          kql:
            description: KQL query selecting alerts whose notifications are suppressed.
            type: str
            required: true
  sensitive_fields:
    description:
      - Dot-separated response fields to redact from output, diffs, and failures.
      - Credential-like keys are always redacted automatically.
    type: list
    elements: str
    default: []
  state:
    description:
      - C(present) creates or updates the window.
      - C(archived) irreversibly archives an existing window.
      - C(absent) deletes the window. Kibana 9.1 and later can delete archived or running windows.
    type: str
    choices: [present, archived, absent]
    default: present
notes:
  - The CRUD and archive contract used by this module requires Elastic Stack 9.1 or later.
  - Exact-name identity through the maintenance-window C(_find) API requires Elastic Stack 9.2 or later.
  - Maintenance windows require an appropriate Elastic subscription and Kibana C(read-maintenance-window) and C(write-maintenance-window) feature privileges.
  - Creation always omits I(id) because Kibana generates the identifier.
  - >-
    Current Kibana releases no longer accept a separate rule-category list.
    Use I(scope.alerting.kql) when alert documents support filtering;
    C(kibana.alert.rule.category) can be used in that KQL.
  - The C(status) return field is calculated by Kibana and can be C(running), C(upcoming), C(finished), C(archived), or C(disabled).
"""

EXAMPLES = r"""
- name: Create a recurring maintenance window
  zupersero.kibana.maintenance_window:
    name: Planned database maintenance
    enabled: true
    schedule:
      start: "2027-01-05T21:00:00.000Z"
      duration: 2h
      timezone: Europe/Copenhagen
      recurring:
        every: 2w
        occurrences: 6
        on_week_day: [TU]
    scope:
      alerting:
        kql: 'kibana.alert.rule.category: "Index threshold"'

- name: Make the window one-time and preserve its other fields
  zupersero.kibana.maintenance_window:
    id: "00000000-0000-0000-0000-000000000000"
    schedule:
      start: "2027-02-01T21:00:00.000Z"
      duration: 3h
      timezone: UTC

- name: Archive a maintenance window
  zupersero.kibana.maintenance_window:
    name: Planned database maintenance
    state: archived

- name: Delete a maintenance window
  zupersero.kibana.maintenance_window:
    id: "00000000-0000-0000-0000-000000000000"
    state: absent
"""

RETURN = r"""
maintenance_window:
  description:
    - Current or resulting maintenance window returned by Kibana.
    - Includes C(name) as an alias for Kibana's C(title), plus server-calculated C(status).
    - C(null) after deletion or when the requested absent window does not exist.
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
from datetime import datetime, timedelta  # noqa: E402
from typing import Any  # noqa: E402

from ansible.module_utils.basic import AnsibleModule  # noqa: E402

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana  # noqa: E402


READ_SUCCESS_CODES = (200,)
FIND_SUCCESS_CODES = (200,)
CREATE_SUCCESS_CODES = (200, 201)
UPDATE_SUCCESS_CODES = (200,)
ARCHIVE_SUCCESS_CODES = (200,)
DELETE_SUCCESS_CODES = (200, 204)
NOT_FOUND_CODES = (404,)
DURATION_PATTERN = re.compile(r"^[1-9][0-9]*[dhms]$")
RECURRENCE_PATTERN = re.compile(r"^[1-9][0-9]*[dwMy]$")
WEEKDAY_PATTERN = re.compile(r"^(?:[+-][1-5])?(?:MO|TU|WE|TH|FR|SA|SU)$")
MANAGED_FIELDS = ("title", "enabled", "schedule", "scope")


def maintenance_window_argument_spec() -> dict[str, dict[str, Any]]:
    """Return the complete typed maintenance-window argument specification."""
    argument_spec = kibana.kibana_argument_spec()
    argument_spec["state"] = dict(
        type="str",
        choices=["present", "archived", "absent"],
        default="present",
    )
    argument_spec.update(
        id=dict(type="str"),
        name=dict(type="str", aliases=["title"]),
        enabled=dict(type="bool"),
        schedule=dict(
            type="dict",
            options=dict(
                start=dict(type="str", required=True),
                duration=dict(type="str", required=True),
                timezone=dict(type="str"),
                recurring=dict(
                    type="dict",
                    options=dict(
                        every=dict(type="str", required=True),
                        end=dict(type="str"),
                        occurrences=dict(type="int"),
                        on_week_day=dict(type="list", elements="str"),
                        on_month_day=dict(type="list", elements="int"),
                        on_month=dict(type="list", elements="int"),
                    ),
                ),
            ),
        ),
        scope=dict(
            type="dict",
            options=dict(
                alerting=dict(
                    type="dict",
                    required=True,
                    options=dict(kql=dict(type="str", required=True)),
                )
            ),
        ),
        sensitive_fields=dict(type="list", elements="str", default=[]),
    )
    return argument_spec


def _validate_utc_timestamp(
    module: AnsibleModule,
    option: str,
    value: str,
) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        module.fail_json(msg=f"`{option}` must be a valid ISO 8601 timestamp: {error}")
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        module.fail_json(msg=f"`{option}` must include the UTC timezone")


def _validate_schedule(module: AnsibleModule) -> None:
    schedule = module.params.get("schedule")
    if schedule is None:
        return
    if not DURATION_PATTERN.fullmatch(schedule["duration"]):
        module.fail_json(
            msg=(
                "`schedule.duration` must be a positive integer followed by "
                "`d`, `h`, `m`, or `s`"
            )
        )
    _validate_utc_timestamp(module, "schedule.start", schedule["start"])
    recurring = schedule.get("recurring")
    if recurring is None:
        return
    if not RECURRENCE_PATTERN.fullmatch(recurring["every"]):
        module.fail_json(
            msg=(
                "`schedule.recurring.every` must be a positive integer "
                "followed by `d`, `w`, `M`, or `y`"
            )
        )
    if recurring.get("end") is not None:
        _validate_utc_timestamp(
            module,
            "schedule.recurring.end",
            recurring["end"],
        )
    if recurring.get("occurrences") is not None and recurring["occurrences"] < 1:
        module.fail_json(
            msg="`schedule.recurring.occurrences` must be at least 1"
        )
    for weekday in recurring.get("on_week_day") or []:
        if not WEEKDAY_PATTERN.fullmatch(weekday):
            module.fail_json(
                msg=(
                    "`schedule.recurring.on_week_day` entries must be a "
                    "weekday such as `MO` or an nth weekday such as `+2TU`"
                )
            )
    for month_day in recurring.get("on_month_day") or []:
        if not 1 <= month_day <= 31:
            module.fail_json(
                msg="`schedule.recurring.on_month_day` entries must be 1 through 31"
            )
    for month in recurring.get("on_month") or []:
        if not 1 <= month <= 12:
            module.fail_json(
                msg="`schedule.recurring.on_month` entries must be 1 through 12"
            )


def _api_schedule(schedule: Mapping[str, Any]) -> dict[str, Any]:
    custom = {
        key: schedule[key]
        for key in ("start", "duration", "timezone")
        if schedule.get(key) is not None
    }
    recurring = schedule.get("recurring")
    if recurring is not None:
        custom["recurring"] = {
            api_name: recurring[module_name]
            for module_name, api_name in (
                ("every", "every"),
                ("end", "end"),
                ("occurrences", "occurrences"),
                ("on_week_day", "onWeekDay"),
                ("on_month_day", "onMonthDay"),
                ("on_month", "onMonth"),
            )
            if recurring.get(module_name) is not None
        }
    return {"custom": custom}


def _api_scope(scope: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "alerting": {
            "query": {
                "kql": scope["alerting"]["kql"],
            }
        }
    }


def _desired_definition(params: Mapping[str, Any]) -> dict[str, Any]:
    desired = {}
    if params.get("name") is not None:
        desired["title"] = params["name"]
    if params.get("enabled") is not None:
        desired["enabled"] = params["enabled"]
    if params.get("schedule") is not None:
        desired["schedule"] = _api_schedule(params["schedule"])
    if params.get("scope") is not None:
        desired["scope"] = _api_scope(params["scope"])
    return desired


def _create_payload(params: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "title": params["name"],
        "schedule": _api_schedule(params["schedule"]),
    }
    if params.get("enabled") is not None:
        payload["enabled"] = params["enabled"]
    if params.get("scope") is not None:
        payload["scope"] = _api_scope(params["scope"])
    return payload


def _normalize_output(window: Any) -> Any:
    if not isinstance(window, Mapping):
        return window
    result = dict(window)
    if isinstance(result.get("title"), str):
        result["name"] = result["title"]
    return result


def _merge_preview(current: Any, desired: Any) -> Any:
    if isinstance(current, Mapping) and isinstance(desired, Mapping):
        result = dict(current)
        result.update(desired)
        return result
    return desired


def _sanitize_result(module: AnsibleModule, result: dict[str, Any]) -> None:
    sensitive_fields = module.params["sensitive_fields"]
    if "maintenance_window" in result:
        result["maintenance_window"] = kibana.sanitize(
            _normalize_output(result["maintenance_window"]),
            sensitive_fields=sensitive_fields,
        )
    if "diff" in result:
        result["diff"] = kibana.sanitize(
            result["diff"],
            sensitive_fields=sensitive_fields,
        )
    module.exit_json(**result)


def _identity(module: AnsibleModule) -> str:
    return module.params.get("id") or module.params.get("name") or "<unknown>"


def _fail_operation(
    module: AnsibleModule,
    operation: str,
    status: int,
    response: Any,
) -> None:
    module.fail_json(
        msg=(
            f"Kibana maintenance window {operation} failed for "
            f"{_identity(module)} with HTTP {status}"
        ),
        status=status,
        response=kibana.sanitize(
            response,
            sensitive_fields=module.params["sensitive_fields"],
        ),
    )


def _validated_window(
    module: AnsibleModule,
    operation: str,
    status: int,
    response: Any,
) -> dict[str, Any]:
    if (
        not isinstance(response, Mapping)
        or not isinstance(response.get("id"), str)
        or not isinstance(response.get("title"), str)
        or not isinstance(response.get("enabled"), bool)
        or not isinstance(response.get("schedule"), Mapping)
        or response.get("status")
        not in ("running", "upcoming", "finished", "archived", "disabled")
    ):
        module.fail_json(
            msg=(
                f"Kibana maintenance window {operation} returned a malformed "
                f"response for {_identity(module)}"
            ),
            status=status,
            response=kibana.sanitize(
                response,
                sensitive_fields=module.params["sensitive_fields"],
            ),
        )
    return dict(response)


def _find_by_name(
    module: AnsibleModule,
    service: Any,
    sensitive_fields: list[str],
) -> tuple[int, dict[str, Any] | None]:
    name = module.params["name"]
    status, response = service.find(name, sensitive_fields=sensitive_fields)
    if status not in FIND_SUCCESS_CODES:
        _fail_operation(module, "lookup", status, response)
    if (
        not isinstance(response, Mapping)
        or not isinstance(response.get("maintenanceWindows"), list)
    ):
        module.fail_json(
            msg=(
                "Kibana maintenance window lookup returned a malformed "
                f"response for {name}"
            ),
            status=status,
            response=kibana.sanitize(
                response,
                sensitive_fields=sensitive_fields,
            ),
        )
    total = response.get("total")
    if isinstance(total, int) and total > len(response["maintenanceWindows"]):
        module.fail_json(
            msg=(
                f"Maintenance window lookup for `{name}` returned more than "
                "100 candidates; specify `id`"
            )
        )
    matches = [
        item
        for item in response["maintenanceWindows"]
        if isinstance(item, Mapping) and item.get("title") == name
    ]
    if len(matches) > 1:
        module.fail_json(
            msg=(
                f"Multiple maintenance windows named `{name}` exist in space "
                f"`{module.params['space']}`; specify `id`"
            )
        )
    if not matches:
        return 404, None
    return 200, _validated_window(module, "lookup", status, matches[0])


def _read_current(
    module: AnsibleModule,
    service: Any,
    sensitive_fields: list[str],
) -> tuple[int, dict[str, Any] | None]:
    window_id = module.params.get("id")
    if window_id:
        status, response = service.get(
            window_id,
            sensitive_fields=sensitive_fields,
        )
        if status in READ_SUCCESS_CODES:
            return status, _validated_window(module, "read", status, response)
        if status in NOT_FOUND_CODES:
            return status, None
        _fail_operation(module, "read", status, response)
    return _find_by_name(module, service, sensitive_fields)


def run_module(
    module: AnsibleModule,
    client: kibana.KibanaClient | None = None,
) -> None:
    """Reconcile one typed Kibana maintenance window."""
    _validate_schedule(module)
    client = client or kibana.KibanaClient(module)
    service = client.maintenance_windows
    sensitive_fields = module.params["sensitive_fields"]
    status, current = _read_current(module, service, sensitive_fields)
    result = {
        "changed": False,
        "maintenance_window": current,
        "status": status,
    }
    state = module.params["state"]

    if state == "absent":
        if current is None:
            _sanitize_result(module, result)
        result["changed"] = True
        if module._diff:
            result["diff"] = {"before": current, "after": {}}
        if module.check_mode:
            _sanitize_result(module, result)
        status, response = service.delete(
            current["id"],
            sensitive_fields=sensitive_fields,
        )
        if status not in DELETE_SUCCESS_CODES:
            _fail_operation(module, "delete", status, response)
        result.update(status=status, maintenance_window=None)
        _sanitize_result(module, result)

    if state == "archived":
        if current is None:
            module.fail_json(
                msg=(
                    "Cannot archive a missing Kibana maintenance window; "
                    "create it with `state: present` first"
                )
            )
        if current["status"] == "archived":
            _sanitize_result(module, result)
        result["changed"] = True
        if module._diff:
            result["diff"] = {
                "before": {"status": current["status"]},
                "after": {"status": "archived"},
            }
        if module.check_mode:
            preview = dict(current)
            preview["status"] = "archived"
            result["maintenance_window"] = preview
            _sanitize_result(module, result)
        status, response = service.archive(
            current["id"],
            sensitive_fields=sensitive_fields,
        )
        if status not in ARCHIVE_SUCCESS_CODES:
            _fail_operation(module, "archive", status, response)
        result.update(
            status=status,
            maintenance_window=_validated_window(
                module,
                "archive",
                status,
                response,
            ),
        )
        _sanitize_result(module, result)

    if current is None and module.params.get("id") is not None:
        module.fail_json(
            msg=(
                f"Kibana maintenance window `{module.params['id']}` does not "
                "exist; explicit `id` can manage only an existing window. "
                "Omit `id` and provide a unique `name` to create one"
            )
        )

    if current is None:
        if module.params.get("name") is None or module.params.get("schedule") is None:
            module.fail_json(
                msg=(
                    "Creating a Kibana maintenance window requires `name` "
                    "and `schedule`"
                )
            )
        payload = _create_payload(module.params)
        preview = dict(payload)
        preview.setdefault("enabled", True)
        result.update(changed=True, maintenance_window=preview)
        if module._diff:
            result["diff"] = {"before": {}, "after": preview}
        if module.check_mode:
            _sanitize_result(module, result)
        status, response = service.create(
            payload,
            sensitive_fields=sensitive_fields,
        )
        if status not in CREATE_SUCCESS_CODES:
            _fail_operation(module, "create", status, response)
        result.update(
            status=status,
            maintenance_window=_validated_window(
                module,
                "create",
                status,
                response,
            ),
        )
        _sanitize_result(module, result)

    if current["status"] == "archived":
        module.fail_json(
            msg=(
                "An archived Kibana maintenance window cannot be updated; "
                "delete it or use a different name"
            )
        )
    desired = _desired_definition(module.params)
    changed, diff = kibana.comparison_diff(
        current,
        desired,
        sensitive_fields=sensitive_fields,
    )
    if not changed:
        _sanitize_result(module, result)

    result["changed"] = True
    if module._diff:
        result["diff"] = diff
    if module.check_mode:
        result["maintenance_window"] = _merge_preview(current, desired)
        _sanitize_result(module, result)
    status, response = service.update(
        current["id"],
        desired,
        sensitive_fields=sensitive_fields,
    )
    if status not in UPDATE_SUCCESS_CODES:
        _fail_operation(module, "update", status, response)
    result.update(
        status=status,
        maintenance_window=_validated_window(
            module,
            "update",
            status,
            response,
        ),
    )
    _sanitize_result(module, result)


def main() -> None:
    module = AnsibleModule(
        argument_spec=maintenance_window_argument_spec(),
        supports_check_mode=True,
        required_one_of=[["id", "name"]],
        required_together=kibana.kibana_required_together(),
        mutually_exclusive=kibana.kibana_mutually_exclusive(),
    )
    run_module(module)


if __name__ == "__main__":
    main()
