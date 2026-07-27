# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import hashlib
from unittest.mock import Mock

import pytest

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana
from ansible_collections.zupersero.kibana.plugins.modules import dashboard_transfer


class ModuleExit(Exception):
    def __init__(self, result):
        super().__init__()
        self.result = result


class ModuleFailure(Exception):
    def __init__(self, result):
        super().__init__(result["msg"])
        self.result = result


class FakeModule:
    def __init__(self, params, check_mode=False):
        self.params = params
        self.check_mode = check_mode

    def exit_json(self, **result):
        raise ModuleExit(result)

    def fail_json(self, **result):
        raise ModuleFailure(result)


def artifact(
    *,
    include_dashboard=True,
    missing_count=0,
    missing_references=None,
):
    records = [
        (
            '{"type":"index-pattern","id":"view-one",'
            '"attributes":{"title":"Café-*","private_value":"hide"},'
            '"references":[]}'
        )
    ]
    if include_dashboard:
        records.append(
            '{"type":"dashboard","id":"dashboard-one",'
            '"attributes":{"title":"Operations"},'
            '"references":[{"name":"view","type":"index-pattern",'
            '"id":"view-one"}]}'
        )
    records.append(
        '{"exportedCount":%d,"missingRefCount":%d,"missingReferences":%s}'
        % (
            len(records),
            missing_count,
            "[]"
            if missing_references is None
            else (
                '[{"type":"visualization","id":"missing-one"}]'
            ),
        )
    )
    return "\n".join(records) + "\n"


def module_params(**overrides):
    params = {
        "space": "source",
        "target_space": "target",
        "dashboard_id": "dashboard-one",
        "include_references_deep": True,
        "fail_on_missing_references": True,
        "overwrite": False,
        "create_new_copies": False,
        "compatibility_mode": False,
        "return_artifact": False,
        "sensitive_fields": ["attributes.private_value", "meta.pin"],
    }
    params.update(overrides)
    return params


def client_with_service():
    client = Mock()
    client.saved_objects = Mock()
    return client


def run_and_exit(module, client):
    with pytest.raises(ModuleExit) as exit_result:
        dashboard_transfer.run_module(module, client)
    return exit_result.value.result


def success_response(*, destination_id="destination-dashboard"):
    return {
        "success": True,
        "successCount": 2,
        "successResults": [
            {
                "type": "index-pattern",
                "id": "view-one",
                "destinationId": "destination-view",
            },
            {
                "type": "dashboard",
                "id": "dashboard-one",
                "destinationId": destination_id,
                "meta": {"title": "Operations", "pin": "hide"},
            },
        ],
    }


def test_argument_spec_declares_dashboard_workflow_and_safe_defaults():
    spec = dashboard_transfer.dashboard_transfer_argument_spec()

    assert spec["dashboard_id"]["required"] is True
    assert spec["target_space"]["required"] is True
    assert spec["include_references_deep"]["default"] is True
    assert spec["fail_on_missing_references"]["default"] is True
    assert spec["return_artifact"]["default"] is False
    assert dashboard_transfer.TRANSFER_MUTUALLY_EXCLUSIVE == [
        ["create_new_copies", "overwrite"],
        ["create_new_copies", "compatibility_mode"],
    ]
    assert "state" not in spec


def test_check_mode_exports_and_validates_but_never_imports():
    content = artifact()
    module = FakeModule(module_params(), check_mode=True)
    client = client_with_service()
    client.saved_objects.export.return_value = (200, content)

    result = run_and_exit(module, client)

    assert result["changed"] is True
    assert result["source_space"] == "source"
    assert result["target_space"] == "target"
    assert result["dashboard_id"] is None
    assert result["source_dashboard"]["id"] == "dashboard-one"
    assert result["source_dependencies"][0]["attributes"]["private_value"] == (
        kibana.REDACTED
    )
    assert result["dependency_count"] == 1
    assert result["import_status"] is None
    assert "artifact" not in result
    assert result["artifact_sha256"] == hashlib.sha256(
        content.encode("utf-8")
    ).hexdigest()
    client.saved_objects.export.assert_called_once_with(
        {
            "objects": [{"type": "dashboard", "id": "dashboard-one"}],
            "includeReferencesDeep": True,
            "excludeExportDetails": False,
        },
        sensitive_fields=["attributes.private_value", "meta.pin"],
        space_id="source",
    )
    client.saved_objects.import_objects.assert_not_called()


def test_success_preserves_opaque_artifact_and_maps_dashboard_destination():
    content = artifact()
    module = FakeModule(
        module_params(
            overwrite=True,
            compatibility_mode=True,
            return_artifact=True,
        )
    )
    client = client_with_service()
    client.saved_objects.export.return_value = (200, content)
    client.saved_objects.import_objects.return_value = (
        200,
        success_response(),
    )

    result = run_and_exit(module, client)

    assert result["changed"] is True
    assert result["artifact"] == content
    assert result["dashboard_id"] == "destination-dashboard"
    assert result["dashboard"]["id"] == "dashboard-one"
    assert result["dashboard"]["meta"]["pin"] == kibana.REDACTED
    assert result["imported_dependencies"][0]["destinationId"] == (
        "destination-view"
    )
    assert result["success_count"] == 2
    client.saved_objects.import_objects.assert_called_once_with(
        content,
        overwrite=True,
        create_new_copies=False,
        compatibility_mode=True,
        sensitive_fields=["attributes.private_value", "meta.pin"],
        space_id="target",
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"space": ""},
        {"target_space": ""},
        {"target_space": "source"},
        {"create_new_copies": True, "overwrite": True},
        {"create_new_copies": True, "compatibility_mode": True},
    ],
)
def test_invalid_options_fail_before_any_api_request(overrides):
    module = FakeModule(module_params(**overrides))
    client = client_with_service()

    with pytest.raises(ModuleFailure):
        dashboard_transfer.run_module(module, client)

    client.saved_objects.export.assert_not_called()
    client.saved_objects.import_objects.assert_not_called()


def test_missing_dashboard_fails_before_import():
    module = FakeModule(module_params())
    client = client_with_service()
    client.saved_objects.export.return_value = (
        200,
        artifact(include_dashboard=False),
    )

    with pytest.raises(ModuleFailure, match="was not found") as failure:
        dashboard_transfer.run_module(module, client)

    assert failure.value.result["changed"] is False
    client.saved_objects.import_objects.assert_not_called()


def test_missing_references_fail_by_default_and_can_be_allowed():
    content = artifact(
        missing_count=1,
        missing_references=[{"type": "visualization", "id": "missing-one"}],
    )
    client = client_with_service()
    client.saved_objects.export.return_value = (200, content)

    with pytest.raises(ModuleFailure, match="missing reference"):
        dashboard_transfer.run_module(FakeModule(module_params()), client)

    client.saved_objects.import_objects.assert_not_called()

    allowed_client = client_with_service()
    allowed_client.saved_objects.export.return_value = (200, content)
    allowed_client.saved_objects.import_objects.return_value = (
        200,
        success_response(),
    )
    result = run_and_exit(
        FakeModule(module_params(fail_on_missing_references=False)),
        allowed_client,
    )

    assert result["export_details"]["missingRefCount"] == 1


def test_conflict_failure_reports_unchanged_and_object_errors():
    response = {
        "success": False,
        "successCount": 0,
        "errors": [
            {
                "type": "dashboard",
                "id": "dashboard-one",
                "error": {"type": "conflict"},
            }
        ],
    }
    module = FakeModule(module_params())
    client = client_with_service()
    client.saved_objects.export.return_value = (200, artifact())
    client.saved_objects.import_objects.return_value = (200, response)

    with pytest.raises(ModuleFailure, match="1 object error") as failure:
        dashboard_transfer.run_module(module, client)

    assert failure.value.result["changed"] is False
    assert failure.value.result["errors"][0]["error"]["type"] == "conflict"
    assert failure.value.result["success_count"] == 0


def test_partial_import_failure_reports_actual_change():
    response = {
        "success": False,
        "successCount": 1,
        "successResults": [{"type": "index-pattern", "id": "view-one"}],
        "errors": [
            {
                "type": "dashboard",
                "id": "dashboard-one",
                "error": {"type": "conflict"},
            }
        ],
    }
    module = FakeModule(module_params())
    client = client_with_service()
    client.saved_objects.export.return_value = (200, artifact())
    client.saved_objects.import_objects.return_value = (200, response)

    with pytest.raises(ModuleFailure) as failure:
        dashboard_transfer.run_module(module, client)

    assert failure.value.result["changed"] is True
    assert failure.value.result["success_count"] == 1


@pytest.mark.parametrize(
    ("export_status", "export_response", "message"),
    [
        (404, {"message": "missing space"}, "export failed with HTTP 404"),
        (200, {"unexpected": "json"}, "malformed non-NDJSON"),
        (200, '{"type":\n', "malformed NDJSON"),
        (
            200,
            '{"type":"dashboard","id":"dashboard-one"}\n',
            "omitted its export-details",
        ),
    ],
)
def test_export_errors_fail_without_import(
    export_status,
    export_response,
    message,
):
    module = FakeModule(module_params())
    client = client_with_service()
    client.saved_objects.export.return_value = (
        export_status,
        export_response,
    )

    with pytest.raises(ModuleFailure, match=message):
        dashboard_transfer.run_module(module, client)

    client.saved_objects.import_objects.assert_not_called()


def test_import_http_error_is_sanitized_and_reports_no_change():
    module = FakeModule(module_params())
    client = client_with_service()
    client.saved_objects.export.return_value = (200, artifact())
    client.saved_objects.import_objects.return_value = (
        400,
        {"message": "bad import", "access_token": "must-not-leak"},
    )

    with pytest.raises(ModuleFailure) as failure:
        dashboard_transfer.run_module(module, client)

    assert failure.value.result["changed"] is False
    assert failure.value.result["import_status"] == 400
    assert failure.value.result["response"]["access_token"] == kibana.REDACTED


@pytest.mark.parametrize(
    "response",
    [
        "not-json",
        {},
        {"success": True, "successCount": "two"},
        {"success": True, "successCount": 2, "successResults": {}},
        {
            "success": True,
            "successCount": 2,
            "successResults": [{"type": "index-pattern", "id": "view-one"}],
        },
    ],
)
def test_malformed_import_responses_fail_with_changed_unknown(response):
    module = FakeModule(module_params())
    client = client_with_service()
    client.saved_objects.export.return_value = (200, artifact())
    client.saved_objects.import_objects.return_value = (200, response)

    with pytest.raises(ModuleFailure) as failure:
        dashboard_transfer.run_module(module, client)

    assert failure.value.result["changed"] is True
