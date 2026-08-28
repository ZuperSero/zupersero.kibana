# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest.mock import Mock

import pytest

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana
from ansible_collections.zupersero.kibana.plugins.modules import package_policy


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
        "name": "System integration",
        "namespace": "default",
        "package": "system",
        "package_version": "1.49.0",
        "policy_id": "agent-policy",
        "description": None,
        "inputs": {"system/metrics": {"enabled": True}},
        "vars": {"secret_token": "do-not-leak"},
        "replace": False,
        "force": False,
        "sensitive_fields": ["vars.secret_token"],
        "state": "present",
        "space": "default",
    }
    params.update(overrides)
    return params


def policy_response(**overrides):
    result = {
        "id": "generated-policy-id",
        "name": "System integration",
        "namespace": "default",
        "description": "",
        "package": {"name": "system", "version": "1.49.0"},
        "policy_id": "agent-policy",
        "inputs": {"system/metrics": {"enabled": True}},
        "vars": {"secret_token": "do-not-leak"},
        "revision": 1,
    }
    result.update(overrides)
    return result


def client_with_services():
    client = Mock()
    client.package_policies = Mock()
    client.agent_policies = Mock()
    client.epm = Mock()
    client.package_policies.list.return_value = (200, {"items": []})
    return client


def run_and_exit(module, client):
    with pytest.raises(ModuleExit) as exit_result:
        package_policy.run_module(module, client)
    return exit_result.value.result


def configure_validation(client):
    client.agent_policies.get.return_value = (200, {"id": "agent-policy"})
    client.epm.list_installed.return_value = (
        200,
        {"items": [{"name": "system", "version": "1.49.0"}]},
    )


def test_argument_spec_marks_package_values_secret_and_replace():
    spec = package_policy.package_policy_argument_spec()
    assert spec["inputs"]["no_log"] is True
    assert spec["vars"]["no_log"] is True
    assert spec["namespace"]["default"] == "default"
    assert spec["replace"]["default"] is False


def test_create_check_mode_validates_dependencies_and_redacts_secret():
    module = FakeModule(module_params(), check_mode=True, diff=True)
    client = client_with_services()
    configure_validation(client)

    result = run_and_exit(module, client)

    assert result["changed"] is True
    assert result["package_policy"]["package"] == {
        "name": "system",
        "version": "1.49.0",
    }
    assert result["package_policy"]["vars"]["secret_token"] == kibana.REDACTED
    client.package_policies.create.assert_not_called()


def test_create_returns_generated_id_and_is_idempotent_after_read():
    module = FakeModule(module_params())
    client = client_with_services()
    configure_validation(client)
    client.package_policies.create.return_value = (200, policy_response())

    result = run_and_exit(module, client)

    assert result["changed"] is True
    assert result["package_policy"]["id"] == "generated-policy-id"

    module = FakeModule(module_params(id="generated-policy-id"))
    client.package_policies.get.return_value = (200, policy_response())
    result = run_and_exit(module, client)
    assert result["changed"] is False
    client.package_policies.update.assert_not_called()


def test_update_preserves_omitted_nested_values_and_allows_explicit_clear():
    module = FakeModule(module_params(id="generated-policy-id", inputs=None, vars={}))
    client = client_with_services()
    client.package_policies.get.return_value = (200, policy_response())
    configure_validation(client)
    client.package_policies.update.return_value = (
        200,
        policy_response(vars={}, inputs={"system/metrics": {"enabled": True}}),
    )

    result = run_and_exit(module, client)

    assert result["changed"] is True
    payload = client.package_policies.update.call_args.args[1]
    assert payload["inputs"] == {"system/metrics": {"enabled": True}}
    assert payload["vars"] == {}


def test_replace_clears_omitted_nested_values_in_check_mode():
    module = FakeModule(
        module_params(id="generated-policy-id", inputs=None, vars=None, replace=True),
        check_mode=True,
    )
    client = client_with_services()
    client.package_policies.get.return_value = (200, policy_response())
    configure_validation(client)

    result = run_and_exit(module, client)

    assert result["changed"] is True
    assert result["package_policy"]["inputs"] == {}
    assert result["package_policy"]["vars"] == {}
    client.package_policies.update.assert_not_called()


def test_missing_agent_policy_fails_before_package_mutation():
    module = FakeModule(module_params())
    client = client_with_services()
    client.agent_policies.get.return_value = (404, {"message": "missing"})

    with pytest.raises(ModuleFailure, match="agent policy `agent-policy` does not exist"):
        package_policy.run_module(module, client)
    client.epm.list_installed.assert_not_called()
    client.package_policies.create.assert_not_called()


def test_missing_installed_package_fails_without_mutation():
    module = FakeModule(module_params())
    client = client_with_services()
    client.agent_policies.get.return_value = (200, {"id": "agent-policy"})
    client.epm.list_installed.return_value = (200, {"items": []})

    with pytest.raises(ModuleFailure, match="package `system` version `1.49.0` is not installed"):
        package_policy.run_module(module, client)
    client.package_policies.create.assert_not_called()


def test_delete_is_check_safe_and_repeated_absent_is_unchanged():
    module = FakeModule(module_params(id="generated-policy-id", state="absent"), check_mode=True, diff=True)
    client = client_with_services()
    client.package_policies.get.return_value = (200, policy_response())

    result = run_and_exit(module, client)

    assert result["changed"] is True
    assert result["diff"]["after"] == {}
    client.package_policies.delete.assert_not_called()

    module = FakeModule(module_params(id="generated-policy-id", state="absent"))
    client.package_policies.get.return_value = (404, {"message": "missing"})
    result = run_and_exit(module, client)
    assert result["changed"] is False
