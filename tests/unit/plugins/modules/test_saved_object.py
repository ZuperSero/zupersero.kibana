# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest.mock import Mock

import pytest

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana
from ansible_collections.zupersero.kibana.plugins.modules import saved_object


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
        "type": "index-pattern",
        "id": "phase1-object",
        "attributes": {
            "title": "logs-*",
            "private_value": "must-not-leak",
        },
        "references": None,
        "force_delete": False,
        "sensitive_fields": ["attributes.private_value"],
        "state": "present",
    }
    params.update(overrides)
    return params


def object_response(title="logs-*", private_value="must-not-leak", **extra):
    return {
        "id": "phase1-object",
        "type": "index-pattern",
        "attributes": {
            "title": title,
            "private_value": private_value,
            "server_owned": "preserved",
        },
        "references": [],
        **extra,
    }


def client_with_service():
    client = Mock()
    client.saved_objects = Mock()
    return client


def run_and_exit(module, client):
    with pytest.raises(ModuleExit) as exit_result:
        saved_object.run_module(module, client)
    return exit_result.value.result


def test_argument_spec_and_conditional_validation_contract():
    spec = saved_object.saved_object_argument_spec()

    assert spec["type"]["required"] is True
    assert spec["id"]["required"] is True
    assert spec["attributes"]["type"] == "dict"
    assert spec["references"]["options"]["id"]["required"] is True
    assert spec["references"]["options"]["type"]["required"] is True
    assert spec["references"]["options"]["name"]["required"] is True
    assert saved_object.SAVED_OBJECT_REQUIRED_IF == [
        ["state", "present", ["attributes"]]
    ]


def test_create_check_mode_predicts_change_diff_and_redacts_sensitive_fields():
    module = FakeModule(module_params(), check_mode=True, diff=True)
    client = client_with_service()
    client.saved_objects.get.return_value = (404, {"message": "missing"})

    result = run_and_exit(module, client)

    assert result["changed"] is True
    assert result["status"] == 404
    assert result["saved_object"]["id"] == "phase1-object"
    assert result["saved_object"]["attributes"]["private_value"] == kibana.REDACTED
    assert result["diff"]["after"]["attributes"]["private_value"] == kibana.REDACTED
    client.saved_objects.create.assert_not_called()


def test_create_returns_validated_server_object():
    module = FakeModule(module_params())
    client = client_with_service()
    created = object_response()
    client.saved_objects.get.return_value = (404, {"message": "missing"})
    client.saved_objects.create.return_value = (200, created)

    result = run_and_exit(module, client)

    assert result["changed"] is True
    assert result["status"] == 200
    assert result["saved_object"]["attributes"]["title"] == "logs-*"
    assert result["saved_object"]["attributes"]["private_value"] == kibana.REDACTED
    client.saved_objects.create.assert_called_once_with(
        "index-pattern",
        "phase1-object",
        {
            "attributes": {
                "title": "logs-*",
                "private_value": "must-not-leak",
            }
        },
        sensitive_fields=["attributes.private_value"],
    )


def test_read_return_is_idempotent_and_preserves_server_fields():
    module = FakeModule(module_params())
    client = client_with_service()
    client.saved_objects.get.return_value = (200, object_response(updated_at="later"))

    result = run_and_exit(module, client)

    assert result["changed"] is False
    assert result["saved_object"]["updated_at"] == "later"
    assert result["saved_object"]["attributes"]["server_owned"] == "preserved"
    client.saved_objects.update.assert_not_called()


def test_update_check_mode_merges_preview_without_mutating():
    module = FakeModule(module_params(), check_mode=True, diff=True)
    client = client_with_service()
    client.saved_objects.get.return_value = (
        200,
        object_response(title="old-logs-*"),
    )

    result = run_and_exit(module, client)

    assert result["changed"] is True
    assert result["saved_object"]["attributes"]["title"] == "logs-*"
    assert result["saved_object"]["attributes"]["server_owned"] == "preserved"
    assert result["diff"]["before"]["attributes"]["title"] == "old-logs-*"
    assert result["diff"]["after"]["attributes"]["title"] == "logs-*"
    client.saved_objects.update.assert_not_called()


def test_update_returns_changed_server_object_and_manages_references():
    references = [{"id": "logs", "type": "index-pattern", "name": "dataView"}]
    module = FakeModule(module_params(references=references))
    client = client_with_service()
    client.saved_objects.get.return_value = (
        200,
        object_response(title="old-logs-*"),
    )
    updated = object_response(references=references)
    client.saved_objects.update.return_value = (200, updated)

    result = run_and_exit(module, client)

    assert result["changed"] is True
    assert result["saved_object"]["references"] == references
    client.saved_objects.update.assert_called_once_with(
        "index-pattern",
        "phase1-object",
        {
            "attributes": {
                "title": "logs-*",
                "private_value": "must-not-leak",
                "server_owned": "preserved",
            },
            "references": references,
        },
        sensitive_fields=["attributes.private_value"],
    )


def test_update_preserves_omitted_attributes_and_references_in_api_payload():
    current_references = [
        {"id": "logs", "type": "index-pattern", "name": "dataView"}
    ]
    module = FakeModule(
        module_params(
            attributes={
                "title": "logs-*",
                "private_value": "must-not-leak",
            }
        )
    )
    client = client_with_service()
    current = object_response(
        title="old-logs-*",
        references=current_references,
    )
    client.saved_objects.get.return_value = (200, current)
    client.saved_objects.update.return_value = (
        200,
        object_response(references=current_references),
    )

    run_and_exit(module, client)

    client.saved_objects.update.assert_called_once_with(
        "index-pattern",
        "phase1-object",
        {
            "attributes": {
                "title": "logs-*",
                "private_value": "must-not-leak",
                "server_owned": "preserved",
            },
            "references": current_references,
        },
        sensitive_fields=["attributes.private_value"],
    )


def test_delete_check_mode_returns_current_object_without_mutating():
    module = FakeModule(
        module_params(state="absent", attributes=None),
        check_mode=True,
        diff=True,
    )
    client = client_with_service()
    client.saved_objects.get.return_value = (200, object_response())

    result = run_and_exit(module, client)

    assert result["changed"] is True
    assert result["saved_object"]["id"] == "phase1-object"
    assert result["diff"]["after"] == {}
    client.saved_objects.delete.assert_not_called()


def test_delete_and_repeated_delete_are_idempotent():
    module = FakeModule(module_params(state="absent", attributes=None))
    client = client_with_service()
    client.saved_objects.get.return_value = (200, object_response())
    client.saved_objects.delete.return_value = (204, None)

    result = run_and_exit(module, client)

    assert result == {"changed": True, "saved_object": None, "status": 204}
    client.saved_objects.delete.assert_called_once_with(
        "index-pattern",
        "phase1-object",
        force=False,
        sensitive_fields=["attributes.private_value"],
    )

    missing_module = FakeModule(module_params(state="absent", attributes=None))
    missing_client = client_with_service()
    missing_client.saved_objects.get.return_value = (404, {"message": "missing"})

    missing_result = run_and_exit(missing_module, missing_client)

    assert missing_result == {
        "changed": False,
        "saved_object": None,
        "status": 404,
    }
    missing_client.saved_objects.delete.assert_not_called()


def test_api_error_has_operation_context_and_redacts_response():
    module = FakeModule(module_params())
    client = client_with_service()
    client.saved_objects.get.return_value = (
        403,
        {
            "message": "forbidden",
            "attributes": {"private_value": "must-not-leak"},
            "access_token": "automatic-secret",
        },
    )

    with pytest.raises(ModuleFailure) as failure:
        saved_object.run_module(module, client)

    result = failure.value.result
    assert "read failed for index-pattern/phase1-object with HTTP 403" in result["msg"]
    assert result["response"]["attributes"]["private_value"] == kibana.REDACTED
    assert result["response"]["access_token"] == kibana.REDACTED


@pytest.mark.parametrize(
    "response",
    [
        "not-json",
        {"id": "phase1-object", "type": "index-pattern"},
        {"id": "phase1-object", "type": "index-pattern", "attributes": []},
    ],
)
def test_malformed_read_response_fails_with_actionable_context(response):
    module = FakeModule(module_params())
    client = client_with_service()
    client.saved_objects.get.return_value = (200, response)

    with pytest.raises(ModuleFailure) as failure:
        saved_object.run_module(module, client)

    assert "read returned a malformed response" in failure.value.result["msg"]
    assert failure.value.result["status"] == 200
