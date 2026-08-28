# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest.mock import Mock

import pytest

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana
from ansible_collections.zupersero.kibana.plugins.modules import maintenance_window


class ModuleExit(Exception):
    def __init__(self, result):
        super().__init__()
        self.result = result


class ModuleFailure(Exception):
    def __init__(self, result):
        super().__init__(result["msg"])
        self.result = result


class FakeModule:
    def __init__(self, params, check_mode=False, diff=False):
        self.params = params
        self.check_mode = check_mode
        self._diff = diff

    def exit_json(self, **result):
        raise ModuleExit(result)

    def fail_json(self, **result):
        raise ModuleFailure(result)


def module_params(**overrides):
    params = {
        "id": None,
        "name": "Phase 1 window",
        "enabled": True,
        "schedule": {
            "start": "2099-01-05T10:00:00.000Z",
            "duration": "2h",
            "timezone": "Europe/Copenhagen",
            "recurring": {
                "every": "2w",
                "occurrences": 3,
                "end": None,
                "on_week_day": ["MO", "+2TU"],
                "on_month_day": None,
                "on_month": None,
            },
        },
        "scope": {"alerting": {"kql": "private: must-not-leak"}},
        "sensitive_fields": ["scope.alerting.query.kql"],
        "state": "present",
        "space": "operations",
    }
    params.update(overrides)
    return params


def window_response(**overrides):
    result = {
        "id": "window-id",
        "title": "Phase 1 window",
        "enabled": True,
        "schedule": {
            "custom": {
                "start": "2099-01-05T10:00:00.000Z",
                "duration": "2h",
                "timezone": "Europe/Copenhagen",
                "recurring": {
                    "every": "2w",
                    "occurrences": 3,
                    "onWeekDay": ["MO", "+2TU"],
                },
            }
        },
        "scope": {
            "alerting": {"query": {"kql": "private: must-not-leak"}}
        },
        "status": "upcoming",
        "created_at": "2026-01-01T00:00:00.000Z",
        "updated_at": "2026-01-01T00:00:00.000Z",
    }
    result.update(overrides)
    return result


def client_with_service():
    client = Mock()
    client.maintenance_windows = Mock()
    return client


def run_and_exit(module, client):
    with pytest.raises(ModuleExit) as exit_result:
        maintenance_window.run_module(module, client)
    return exit_result.value.result


def test_argument_spec_models_recurrence_and_archive_state():
    spec = maintenance_window.maintenance_window_argument_spec()
    recurring = spec["schedule"]["options"]["recurring"]["options"]

    assert spec["name"]["aliases"] == ["title"]
    assert recurring["every"]["required"] is True
    assert recurring["on_week_day"]["elements"] == "str"
    assert spec["state"]["choices"] == ["present", "archived", "absent"]


@pytest.mark.parametrize(
    ("schedule", "message"),
    [
        (
            {"start": "not-a-date", "duration": "2h", "recurring": None},
            "valid ISO 8601",
        ),
        (
            {
                "start": "2099-01-05T10:00:00.000Z",
                "duration": "zero",
                "recurring": None,
            },
            "schedule.duration",
        ),
        (
            {
                "start": "2099-01-05T10:00:00.000Z",
                "duration": "2h",
                "recurring": {
                    "every": "hourly",
                    "end": None,
                    "occurrences": None,
                    "on_week_day": None,
                    "on_month_day": None,
                    "on_month": None,
                },
            },
            "recurring.every",
        ),
    ],
)
def test_schedule_validation_is_actionable(schedule, message):
    module = FakeModule(module_params(schedule=schedule))

    with pytest.raises(ModuleFailure, match=message):
        maintenance_window.run_module(module, client_with_service())


def test_create_check_mode_builds_api_shape_and_redacts_scope():
    module = FakeModule(module_params(), check_mode=True, diff=True)
    client = client_with_service()
    client.maintenance_windows.find.return_value = (
        200,
        {"maintenanceWindows": [], "page": 1, "per_page": 100, "total": 0},
    )

    result = run_and_exit(module, client)

    assert result["changed"] is True
    custom = result["maintenance_window"]["schedule"]["custom"]
    assert custom["recurring"]["onWeekDay"] == ["MO", "+2TU"]
    assert (
        result["maintenance_window"]["scope"]["alerting"]["query"]["kql"]
        == kibana.REDACTED
    )
    client.maintenance_windows.create.assert_not_called()


def test_create_returns_generated_id_and_name_alias():
    module = FakeModule(module_params())
    client = client_with_service()
    client.maintenance_windows.find.return_value = (
        200,
        {"maintenanceWindows": [], "page": 1, "per_page": 100, "total": 0},
    )
    client.maintenance_windows.create.return_value = (200, window_response())

    result = run_and_exit(module, client)

    assert result["maintenance_window"]["id"] == "window-id"
    assert result["maintenance_window"]["name"] == "Phase 1 window"
    assert result["status"] == 200


def test_missing_explicit_id_never_creates_or_duplicates_a_window():
    module = FakeModule(module_params(id="missing-window"))
    client = client_with_service()
    client.maintenance_windows.get.return_value = (404, {"message": "missing"})

    for _attempt in range(2):
        with pytest.raises(
            ModuleFailure,
            match="explicit `id` can manage only an existing window",
        ):
            maintenance_window.run_module(module, client)

    assert client.maintenance_windows.get.call_count == 2
    client.maintenance_windows.create.assert_not_called()
    client.maintenance_windows.find.assert_not_called()


def test_name_lookup_is_idempotent_and_requires_unique_exact_match():
    module = FakeModule(module_params())
    client = client_with_service()
    current = window_response()
    client.maintenance_windows.find.return_value = (
        200,
        {"maintenanceWindows": [current], "page": 1, "per_page": 100, "total": 1},
    )

    result = run_and_exit(module, client)
    assert result["changed"] is False
    assert result["maintenance_window"]["status"] == "upcoming"

    duplicate_client = client_with_service()
    duplicate_client.maintenance_windows.find.return_value = (
        200,
        {
            "maintenanceWindows": [current, window_response(id="second")],
            "page": 1,
            "per_page": 100,
            "total": 2,
        },
    )
    with pytest.raises(ModuleFailure, match="Multiple maintenance windows"):
        maintenance_window.run_module(module, duplicate_client)


def test_schedule_update_clears_recurrence_and_preserves_omitted_scope():
    one_time_schedule = {
        "start": "2099-02-01T10:00:00.000Z",
        "duration": "3h",
        "timezone": "UTC",
        "recurring": None,
    }
    module = FakeModule(
        module_params(
            id="window-id",
            name=None,
            enabled=None,
            scope=None,
            schedule=one_time_schedule,
        )
    )
    client = client_with_service()
    current = window_response()
    client.maintenance_windows.get.return_value = (200, current)
    updated = window_response(
        schedule={
            "custom": {
                "start": "2099-02-01T10:00:00.000Z",
                "duration": "3h",
                "timezone": "UTC",
            }
        }
    )
    client.maintenance_windows.update.return_value = (200, updated)

    result = run_and_exit(module, client)

    assert result["changed"] is True
    payload = client.maintenance_windows.update.call_args.args[1]
    assert "recurring" not in payload["schedule"]["custom"]
    assert "scope" not in payload


def test_archive_check_mode_and_live_archive_are_idempotent():
    module = FakeModule(
        module_params(
            id="window-id",
            name=None,
            enabled=None,
            schedule=None,
            scope=None,
            state="archived",
        ),
        check_mode=True,
        diff=True,
    )
    client = client_with_service()
    client.maintenance_windows.get.return_value = (200, window_response())

    result = run_and_exit(module, client)
    assert result["changed"] is True
    assert result["maintenance_window"]["status"] == "archived"
    client.maintenance_windows.archive.assert_not_called()

    live_module = FakeModule(module.params)
    live_client = client_with_service()
    live_client.maintenance_windows.get.return_value = (200, window_response())
    live_client.maintenance_windows.archive.return_value = (
        200,
        window_response(status="archived"),
    )
    live_result = run_and_exit(live_module, live_client)
    assert live_result["changed"] is True
    assert live_result["maintenance_window"]["status"] == "archived"

    again_client = client_with_service()
    again_client.maintenance_windows.get.return_value = (
        200,
        window_response(status="archived"),
    )
    again_result = run_and_exit(live_module, again_client)
    assert again_result["changed"] is False


def test_delete_and_repeated_delete_are_idempotent():
    module = FakeModule(
        module_params(
            id="window-id",
            name=None,
            enabled=None,
            schedule=None,
            scope=None,
            state="absent",
        )
    )
    client = client_with_service()
    client.maintenance_windows.get.return_value = (200, window_response())
    client.maintenance_windows.delete.return_value = (204, None)

    result = run_and_exit(module, client)
    assert result == {
        "changed": True,
        "maintenance_window": None,
        "status": 204,
    }

    missing_client = client_with_service()
    missing_client.maintenance_windows.get.return_value = (404, {})
    missing_result = run_and_exit(module, missing_client)
    assert missing_result == {
        "changed": False,
        "maintenance_window": None,
        "status": 404,
    }


def test_api_error_and_malformed_response_are_actionable_and_sanitized():
    module = FakeModule(module_params(id="window-id"))
    client = client_with_service()
    client.maintenance_windows.get.return_value = (
        403,
        {
            "scope": {
                "alerting": {"query": {"kql": "private: must-not-leak"}}
            },
            "access_token": "automatic-secret",
        },
    )
    with pytest.raises(ModuleFailure) as failure:
        maintenance_window.run_module(module, client)
    assert "read failed for window-id with HTTP 403" in failure.value.result["msg"]
    assert failure.value.result["response"]["access_token"] == kibana.REDACTED
    assert (
        failure.value.result["response"]["scope"]["alerting"]["query"]["kql"]
        == kibana.REDACTED
    )

    malformed_client = client_with_service()
    malformed_client.maintenance_windows.get.return_value = (200, {"id": "window-id"})
    with pytest.raises(ModuleFailure, match="malformed"):
        maintenance_window.run_module(module, malformed_client)


def test_malformed_create_update_and_archive_responses_are_rejected():
    create_module = FakeModule(module_params())
    create_client = client_with_service()
    create_client.maintenance_windows.find.return_value = (
        200,
        {"maintenanceWindows": [], "page": 1, "per_page": 100, "total": 0},
    )
    create_client.maintenance_windows.create.return_value = (
        200,
        {"id": "window-id"},
    )
    with pytest.raises(ModuleFailure, match="create returned a malformed response"):
        maintenance_window.run_module(create_module, create_client)

    update_module = FakeModule(
        module_params(
            id="window-id",
            name=None,
            enabled=False,
            schedule=None,
            scope=None,
        )
    )
    update_client = client_with_service()
    update_client.maintenance_windows.get.return_value = (
        200,
        window_response(),
    )
    update_client.maintenance_windows.update.return_value = (
        200,
        {"id": "window-id"},
    )
    with pytest.raises(ModuleFailure, match="update returned a malformed response"):
        maintenance_window.run_module(update_module, update_client)

    archive_module = FakeModule(
        module_params(
            id="window-id",
            name=None,
            enabled=None,
            schedule=None,
            scope=None,
            state="archived",
        )
    )
    archive_client = client_with_service()
    archive_client.maintenance_windows.get.return_value = (
        200,
        window_response(),
    )
    archive_client.maintenance_windows.archive.return_value = (
        200,
        {"id": "window-id"},
    )
    with pytest.raises(ModuleFailure, match="archive returned a malformed response"):
        maintenance_window.run_module(archive_module, archive_client)
