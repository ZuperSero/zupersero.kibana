# Copyright (c) 2026, zupersero

from __future__ import annotations

from unittest.mock import Mock

import pytest

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana
from ansible_collections.zupersero.kibana.plugins.modules import agent_policy, fleet_package


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


def policy_params(**overrides):
    params = {
        "id": None,
        "name": "Applications",
        "description": "Managed policy",
        "namespace": "application",
        "monitoring_enabled": ["logs", "metrics"],
        "data_output_id": None,
        "monitoring_output_id": None,
        "fleet_server_host_id": None,
        "download_source_id": None,
        "inactivity_timeout": None,
        "unenroll_timeout": None,
        "keep_monitoring_alive": None,
        "global_data_tags": None,
        "overrides": None,
        "required_versions": None,
        "agent_features": None,
        "force": False,
        "sensitive_fields": [],
        "state": "present",
        "space": "default",
    }
    params.update(overrides)
    return params


def package_params(**overrides):
    params = {
        "name": "system",
        "package_version": None,
        "prerelease": False,
        "force": False,
        "ignore_constraints": False,
        "ignore_mapping_update_errors": False,
        "skip_data_stream_rollover": False,
        "keep_policies_up_to_date": False,
        "sensitive_fields": [],
        "state": "present",
        "space": "default",
    }
    params.update(overrides)
    return params


def run(module, target, client):
    with pytest.raises(ModuleExit) as exit_result:
        target.run_module(module, client)
    return exit_result.value.result


def test_argument_specs_include_fleet_options_and_secret_safe_fields():
    policy_spec = agent_policy.agent_policy_argument_spec()
    package_spec = fleet_package.fleet_package_argument_spec()

    assert policy_spec["monitoring_enabled"]["choices"] == ["logs", "metrics", "traces"]
    assert package_spec["package_version"]["aliases"] == ["version"]
    assert package_spec["sensitive_fields"]["default"] == []
    assert package_spec["api_key"]["no_log"] is True


def test_agent_policy_create_check_mode_preserves_safe_preview():
    module = FakeModule(policy_params(), check_mode=True, diff=True)
    client = Mock()
    client.agent_policies = Mock()
    client.agent_policies.list.return_value = (200, {"items": []})

    result = run(module, agent_policy, client)

    assert result["changed"] is True
    assert result["agent_policy"]["name"] == "Applications"
    assert result["agent_policy"]["namespace"] == "application"
    assert result["diff"]["before"] == {}
    client.agent_policies.create.assert_not_called()


def test_agent_policy_update_merges_omitted_fields_and_is_idempotent():
    current = {
        "id": "policy-id",
        "name": "Applications",
        "description": "old",
        "namespace": "application",
        "monitoring_enabled": ["logs"],
        "data_output_id": "output-id",
        "server_owned": True,
    }
    client = Mock()
    client.agent_policies = Mock()
    client.agent_policies.get.return_value = (200, {"item": current})
    client.agent_policies.update.return_value = (200, {"item": {**current, "description": "new"}})

    result = run(
        FakeModule(policy_params(id="policy-id", name=None, description="new", monitoring_enabled=None)),
        agent_policy,
        client,
    )

    assert result["changed"] is True
    payload = client.agent_policies.update.call_args.args[1]
    assert payload["data_output_id"] == "output-id"
    assert payload["monitoring_enabled"] == ["logs"]
    assert "server_owned" not in payload

    client.agent_policies.update.reset_mock()
    client.agent_policies.get.return_value = (200, {"item": {**current, "description": "new"}})
    result = run(
        FakeModule(policy_params(id="policy-id", name=None, description="new", monitoring_enabled=None)),
        agent_policy,
        client,
    )
    assert result["changed"] is False
    client.agent_policies.update.assert_not_called()


def test_agent_policy_delete_check_mode_passes_force_and_is_idempotent():
    current = {"id": "policy-id", "name": "Applications", "namespace": "application"}
    client = Mock()
    client.agent_policies = Mock()
    client.agent_policies.get.return_value = (200, current)

    result = run(
        FakeModule(policy_params(id="policy-id", name=None, state="absent", force=True), check_mode=True),
        agent_policy,
        client,
    )
    assert result["changed"] is True
    client.agent_policies.delete.assert_not_called()

    client.agent_policies.get.return_value = (404, {"message": "missing"})
    result = run(
        FakeModule(policy_params(id="policy-id", name=None, state="absent", force=True)),
        agent_policy,
        client,
    )
    assert result["changed"] is False


def test_fleet_package_install_check_mode_and_idempotency():
    client = Mock()
    client.epm = Mock()
    client.epm.list_installed.return_value = (200, {"items": []})
    result = run(FakeModule(package_params(package_version="1.0.0"), check_mode=True, diff=True), fleet_package, client)

    assert result["changed"] is True
    assert result["operation"] == "install"
    client.epm.install.assert_not_called()

    client.epm.list_installed.return_value = (200, {"items": [{"name": "system", "version": "1.0.0"}]})
    result = run(FakeModule(package_params(package_version="1.0.0")), fleet_package, client)
    assert result["changed"] is False


def test_fleet_package_upgrade_uses_update_and_uninstall_uses_installed_version():
    client = Mock()
    client.epm = Mock()
    client.epm.list_installed.return_value = (200, {"items": [{"name": "system", "version": "1.0.0"}]})
    client.epm.update.return_value = (200, {"item": {"name": "system", "version": "1.1.0"}})

    result = run(FakeModule(package_params(package_version="1.1.0")), fleet_package, client)
    assert result["changed"] is True
    assert result["operation"] == "update"
    client.epm.update.assert_called_once_with("system", package_version="1.1.0", keep_policies_up_to_date=False)

    client.epm.delete.return_value = (200, {})
    result = run(FakeModule(package_params(state="absent", package_version=None)), fleet_package, client)
    assert result["changed"] is True
    client.epm.delete.assert_called_once_with("system", package_version="1.0.0", force=False)


def test_fleet_package_rejects_malformed_installed_response():
    client = Mock()
    client.epm = Mock()
    client.epm.list_installed.return_value = (200, {"items": "invalid"})

    with pytest.raises(ModuleFailure, match="malformed response"):
        fleet_package.run_module(FakeModule(package_params()), client)


def test_sanitization_redacts_package_response_secrets():
    client = Mock()
    client.epm = Mock()
    client.epm.list_installed.return_value = (200, {"items": []})
    client.epm.install.return_value = (200, {"item": {"name": "system", "token": "private"}})
    module = FakeModule(package_params(), diff=True)
    result = run(module, fleet_package, client)

    # The package API response is normalized by the shared sanitizer.
    assert result["fleet_package"]["item"]["token"] == kibana.REDACTED
