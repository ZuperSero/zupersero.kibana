# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest.mock import Mock

import pytest

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana
from ansible_collections.zupersero.kibana.plugins.modules import (
    saved_objects_import,
)


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


def module_params(**overrides):
    params = {
        "content": (
            '{"type":"dashboard","id":"object / one",'
            '"attributes":{"title":"Café"}}\n'
        ),
        "overwrite": False,
        "create_new_copies": False,
        "compatibility_mode": False,
        "sensitive_fields": ["meta.pin"],
    }
    params.update(overrides)
    return params


def client_with_service():
    client = Mock()
    client.saved_objects = Mock()
    return client


def run_and_exit(module, client=None):
    with pytest.raises(ModuleExit) as exit_result:
        saved_objects_import.run_module(module, client)
    return exit_result.value.result


def test_argument_spec_protects_content_and_declares_action_options():
    spec = saved_objects_import.saved_objects_import_argument_spec()

    assert spec["content"]["required"] is True
    assert spec["content"]["no_log"] is True
    assert spec["overwrite"]["default"] is False
    assert spec["create_new_copies"]["default"] is False
    assert spec["compatibility_mode"]["default"] is False
    assert saved_objects_import.IMPORT_MUTUALLY_EXCLUSIVE == [
        ["create_new_copies", "overwrite"],
        ["create_new_copies", "compatibility_mode"],
    ]
    assert "state" not in spec


def test_import_check_mode_validates_locally_and_predicts_action():
    module = FakeModule(module_params(), check_mode=True)

    result = run_and_exit(module)

    assert result == {
        "changed": True,
        "response": None,
        "success_count": 0,
        "errors": [],
        "success_results": [],
        "status": None,
        "record_count": 1,
    }


def test_import_success_is_explicitly_changed_and_forwards_options():
    response = {
        "success": True,
        "successCount": 1,
        "successResults": [
            {
                "type": "dashboard",
                "id": "object / one",
                "meta": {"pin": "1234"},
            }
        ],
    }
    module = FakeModule(module_params(overwrite=True, compatibility_mode=True))
    client = client_with_service()
    client.saved_objects.import_objects.return_value = (200, response)

    result = run_and_exit(module, client)

    assert result["changed"] is True
    assert result["success_count"] == 1
    assert result["errors"] == []
    assert result["success_results"][0]["meta"]["pin"] == kibana.REDACTED
    assert result["record_count"] == 1
    client.saved_objects.import_objects.assert_called_once_with(
        module.params["content"],
        overwrite=True,
        create_new_copies=False,
        compatibility_mode=True,
        sensitive_fields=["meta.pin"],
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"create_new_copies": True, "overwrite": True},
        {"create_new_copies": True, "compatibility_mode": True},
    ],
)
def test_import_rejects_incompatible_options_before_request(overrides):
    module = FakeModule(module_params(**overrides))
    client = client_with_service()

    with pytest.raises(ModuleFailure, match="mutually exclusive"):
        saved_objects_import.run_module(module, client)

    client.saved_objects.import_objects.assert_not_called()


@pytest.mark.parametrize("content", ["", '{"type":\n', "[]\n"])
def test_import_rejects_malformed_ndjson_before_request(content):
    module = FakeModule(module_params(content=content))
    client = client_with_service()

    with pytest.raises(ModuleFailure, match="Invalid saved object NDJSON"):
        saved_objects_import.run_module(module, client)

    client.saved_objects.import_objects.assert_not_called()


def test_partial_import_failure_reports_actual_changed_status_and_errors():
    response = {
        "success": False,
        "successCount": 1,
        "successResults": [{"type": "dashboard", "id": "one"}],
        "errors": [
            {
                "type": "dashboard",
                "id": "two",
                "error": {"type": "conflict"},
            }
        ],
    }
    module = FakeModule(module_params())
    client = client_with_service()
    client.saved_objects.import_objects.return_value = (200, response)

    with pytest.raises(ModuleFailure) as failure:
        saved_objects_import.run_module(module, client)

    result = failure.value.result
    assert result["changed"] is True
    assert result["success_count"] == 1
    assert result["errors"][0]["id"] == "two"
    assert "1 object error(s)" in result["msg"]


def test_http_failure_reports_no_change_and_sanitizes_response():
    module = FakeModule(module_params())
    client = client_with_service()
    client.saved_objects.import_objects.return_value = (
        400,
        {"message": "bad import", "access_token": "must-not-leak"},
    )

    with pytest.raises(ModuleFailure) as failure:
        saved_objects_import.run_module(module, client)

    result = failure.value.result
    assert result["changed"] is False
    assert result["status"] == 400
    assert result["response"]["access_token"] == kibana.REDACTED


@pytest.mark.parametrize(
    "response",
    [
        "not-json",
        {},
        {"success": True, "successCount": "one"},
        {"success": True, "successCount": 1, "errors": {}},
    ],
)
def test_import_rejects_malformed_success_response(response):
    module = FakeModule(module_params())
    client = client_with_service()
    client.saved_objects.import_objects.return_value = (200, response)

    with pytest.raises(ModuleFailure, match="malformed response") as failure:
        saved_objects_import.run_module(module, client)

    assert failure.value.result["changed"] is True
