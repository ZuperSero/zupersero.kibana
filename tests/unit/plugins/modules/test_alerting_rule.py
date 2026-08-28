# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest.mock import Mock

import pytest

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana
from ansible_collections.zupersero.kibana.plugins.modules import alerting_rule


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
        "id": "phase1-rule",
        "name": "Phase 1 rule",
        "rule_type_id": ".index-threshold",
        "consumer": "stackAlerts",
        "enabled": False,
        "schedule": {"interval": "5m"},
        "params": {"threshold": [100], "private_value": "must-not-leak"},
        "actions": [],
        "tags": ["phase1"],
        "replace": False,
        "sensitive_fields": ["params.private_value"],
        "state": "present",
    }
    params.update(overrides)
    return params


def rule_response(**overrides):
    result = {
        "id": "phase1-rule",
        "name": "Phase 1 rule",
        "rule_type_id": ".index-threshold",
        "consumer": "stackAlerts",
        "enabled": False,
        "schedule": {"interval": "5m"},
        "params": {
            "threshold": [100],
            "private_value": "must-not-leak",
            "server_default": True,
        },
        "actions": [{"id": "preserved-action"}],
        "tags": ["phase1"],
        "revision": 3,
    }
    result.update(overrides)
    return result


def client_with_service():
    client = Mock()
    client.alerting_rules = Mock()
    return client


def run_and_exit(module, client):
    with pytest.raises(ModuleExit) as exit_result:
        alerting_rule.run_module(module, client)
    return exit_result.value.result


def test_argument_spec_protects_action_and_rule_parameters():
    spec = alerting_rule.alerting_rule_argument_spec()

    assert spec["id"]["required"] is True
    assert spec["params"]["no_log"] is True
    assert spec["actions"]["no_log"] is True
    assert spec["actions"]["options"]["params"]["no_log"] is True
    assert spec["schedule"]["options"]["interval"]["required"] is True


def test_create_check_mode_predicts_change_and_redacts_diff():
    module = FakeModule(module_params(), check_mode=True, diff=True)
    client = client_with_service()
    client.alerting_rules.get.return_value = (404, {"message": "missing"})

    result = run_and_exit(module, client)

    assert result["changed"] is True
    assert result["rule"]["enabled"] is False
    assert result["rule"]["params"]["private_value"] == kibana.REDACTED
    assert result["diff"]["after"]["params"]["private_value"] == kibana.REDACTED
    client.alerting_rules.create.assert_not_called()


def test_create_requires_complete_identity_and_returns_server_rule():
    module = FakeModule(module_params())
    client = client_with_service()
    client.alerting_rules.get.return_value = (404, {"message": "missing"})
    client.alerting_rules.create.return_value = (200, rule_response(actions=[]))

    result = run_and_exit(module, client)

    assert result["changed"] is True
    assert result["rule"]["id"] == "phase1-rule"
    client.alerting_rules.create.assert_called_once()

    missing = FakeModule(module_params(consumer=None))
    missing_client = client_with_service()
    missing_client.alerting_rules.get.return_value = (404, {})
    with pytest.raises(ModuleFailure, match="requires"):
        alerting_rule.run_module(missing, missing_client)


def test_read_is_idempotent_and_returns_current_server_fields():
    module = FakeModule(module_params(actions=None))
    client = client_with_service()
    client.alerting_rules.get.return_value = (200, rule_response())

    result = run_and_exit(module, client)

    assert result["changed"] is False
    assert result["rule"]["revision"] == 3
    assert result["rule"]["actions"] == [{"id": "preserved-action"}]
    client.alerting_rules.update.assert_not_called()


def test_actions_ignore_response_only_connector_type_id_for_idempotency():
    action = {
        "id": "connector-id",
        "group": "threshold met",
        "params": {"message": "Alert"},
    }
    module = FakeModule(module_params(actions=[action]))
    client = client_with_service()
    current_action = {**action, "connector_type_id": ".server-log"}
    client.alerting_rules.get.return_value = (
        200,
        rule_response(actions=[current_action]),
    )

    result = run_and_exit(module, client)

    assert result["changed"] is False
    assert result["rule"]["actions"][0]["connector_type_id"] == ".server-log"
    client.alerting_rules.update.assert_not_called()


def test_action_change_strips_response_only_fields_from_update_payload():
    current_action = {
        "id": "connector-id",
        "group": "threshold met",
        "params": {"message": "Old"},
        "connector_type_id": ".server-log",
    }
    desired_action = {
        "id": "connector-id",
        "group": "threshold met",
        "params": {"message": "New"},
    }
    module = FakeModule(module_params(actions=[desired_action]))
    client = client_with_service()
    client.alerting_rules.get.return_value = (
        200,
        rule_response(actions=[current_action]),
    )
    client.alerting_rules.update.return_value = (
        200,
        rule_response(
            actions=[{**desired_action, "connector_type_id": ".server-log"}]
        ),
    )

    result = run_and_exit(module, client)

    assert result["changed"] is True
    payload_action = client.alerting_rules.update.call_args.args[1]["actions"][0]
    assert payload_action == desired_action
    assert "connector_type_id" not in payload_action


def test_update_preserves_omitted_actions_params_and_tags():
    module = FakeModule(
        module_params(
            name=None,
            rule_type_id=None,
            consumer=None,
            enabled=None,
            schedule={"interval": "10m"},
            params=None,
            actions=None,
            tags=None,
        )
    )
    client = client_with_service()
    current = rule_response()
    client.alerting_rules.get.return_value = (200, current)
    updated = rule_response(schedule={"interval": "10m"})
    client.alerting_rules.update.return_value = (200, updated)

    result = run_and_exit(module, client)

    assert result["changed"] is True
    payload = client.alerting_rules.update.call_args.args[1]
    assert payload["actions"] == current["actions"]
    assert payload["params"] == current["params"]
    assert payload["tags"] == current["tags"]


def test_replace_clears_omitted_collections_and_check_mode_is_non_mutating():
    module = FakeModule(
        module_params(
            name=None,
            rule_type_id=None,
            consumer=None,
            enabled=None,
            schedule=None,
            params=None,
            actions=None,
            tags=None,
            replace=True,
        ),
        check_mode=True,
        diff=True,
    )
    client = client_with_service()
    client.alerting_rules.get.return_value = (200, rule_response())

    result = run_and_exit(module, client)

    assert result["changed"] is True
    assert result["rule"]["actions"] == []
    assert result["rule"]["params"] == {}
    assert result["rule"]["tags"] == []
    client.alerting_rules.update.assert_not_called()


def test_enabled_state_uses_action_and_refreshes_current_rule():
    module = FakeModule(
        module_params(
            name=None,
            rule_type_id=None,
            consumer=None,
            enabled=True,
            schedule=None,
            params=None,
            actions=None,
            tags=None,
        )
    )
    client = client_with_service()
    client.alerting_rules.get.side_effect = [
        (200, rule_response()),
        (200, rule_response(enabled=True)),
    ]
    client.alerting_rules.set_enabled.return_value = (204, None)

    result = run_and_exit(module, client)

    assert result["changed"] is True
    assert result["rule"]["enabled"] is True
    client.alerting_rules.set_enabled.assert_called_once_with(
        "phase1-rule",
        True,
        sensitive_fields=["params.private_value"],
    )
    client.alerting_rules.update.assert_not_called()


def test_delete_and_repeated_delete_are_idempotent():
    module = FakeModule(
        module_params(
            state="absent",
            name=None,
            rule_type_id=None,
            consumer=None,
            schedule=None,
            params=None,
            actions=None,
            tags=None,
            enabled=None,
        )
    )
    client = client_with_service()
    client.alerting_rules.get.return_value = (200, rule_response())
    client.alerting_rules.delete.return_value = (204, None)

    result = run_and_exit(module, client)
    assert result == {"changed": True, "rule": None, "status": 204}

    missing_client = client_with_service()
    missing_client.alerting_rules.get.return_value = (404, {"message": "missing"})
    missing_result = run_and_exit(module, missing_client)
    assert missing_result == {"changed": False, "rule": None, "status": 404}


def test_api_error_and_malformed_response_are_actionable_and_sanitized():
    module = FakeModule(module_params())
    client = client_with_service()
    client.alerting_rules.get.return_value = (
        403,
        {
            "message": "forbidden",
            "params": {"private_value": "must-not-leak"},
            "access_token": "automatic-secret",
        },
    )

    with pytest.raises(ModuleFailure) as failure:
        alerting_rule.run_module(module, client)
    assert "read failed for phase1-rule with HTTP 403" in failure.value.result["msg"]
    assert failure.value.result["response"]["access_token"] == kibana.REDACTED
    assert (
        failure.value.result["response"]["params"]["private_value"]
        == kibana.REDACTED
    )

    malformed_client = client_with_service()
    malformed_client.alerting_rules.get.return_value = (200, {"id": "phase1-rule"})
    with pytest.raises(ModuleFailure, match="malformed"):
        alerting_rule.run_module(module, malformed_client)


def test_malformed_create_and_update_responses_fail_with_operation_context():
    create_module = FakeModule(module_params())
    create_client = client_with_service()
    create_client.alerting_rules.get.return_value = (404, {})
    create_client.alerting_rules.create.return_value = (
        200,
        {"id": "phase1-rule"},
    )
    with pytest.raises(ModuleFailure, match="create returned a malformed response"):
        alerting_rule.run_module(create_module, create_client)

    update_module = FakeModule(module_params(schedule={"interval": "10m"}))
    update_client = client_with_service()
    update_client.alerting_rules.get.return_value = (200, rule_response())
    update_client.alerting_rules.update.return_value = (
        200,
        {"id": "phase1-rule"},
    )
    with pytest.raises(ModuleFailure, match="update returned a malformed response"):
        alerting_rule.run_module(update_module, update_client)
