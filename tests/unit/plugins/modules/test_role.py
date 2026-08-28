# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest.mock import Mock

import pytest

from ansible_collections.zupersero.kibana.plugins.modules import role
from ansible_collections.zupersero.kibana.plugins.module_utils import kibana


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


def params(**overrides):
    result = {
        "name": "phase1 role/example",
        "description": "Read role",
        "elasticsearch": {
            "cluster": ["monitor"],
            "indices": [{"names": ["logs-*"], "privileges": ["read"]}],
        },
        "kibana": [{"base": ["read"], "spaces": ["default"]}],
        "metadata": {"owner": "platform"},
        "transient_metadata": None,
        "replace": False,
        "sensitive_fields": ["metadata.private_value"],
        "state": "present",
    }
    result.update(overrides)
    return result


def current_role(**overrides):
    result = {
        "name": "phase1 role/example",
        "description": "Read role",
        "elasticsearch": {
            "cluster": ["monitor"],
            "indices": [{"names": ["logs-*"], "privileges": ["read"]}],
        },
        "kibana": [{"base": ["read"], "spaces": ["default"]}],
        "metadata": {"owner": "platform"},
        "transient_metadata": {"enabled": True},
    }
    result.update(overrides)
    return result


def client_with_service():
    client = Mock()
    client.roles = Mock()
    return client


def run(module, client):
    with pytest.raises(ModuleExit) as exited:
        role.run_module(module, client)
    return exited.value.result


def test_create_check_mode_and_idempotent_update():
    module = FakeModule(params(), check_mode=True, diff=True)
    client = client_with_service()
    client.roles.get.return_value = (404, {"message": "missing"})

    result = run(module, client)

    assert result["changed"] is True
    assert result["role"]["name"] == "phase1 role/example"
    client.roles.create.assert_not_called()

    existing = client_with_service()
    existing.roles.get.return_value = (200, current_role())
    result = run(FakeModule(params()), existing)
    assert result["changed"] is False
    existing.roles.update.assert_not_called()


def test_partial_update_preserves_omitted_top_level_sections():
    module = FakeModule(
        params(
            description="Updated",
            elasticsearch=None,
            kibana=None,
            metadata=None,
            transient_metadata=None,
        )
    )
    client = client_with_service()
    client.roles.get.return_value = (200, current_role())
    client.roles.update.return_value = (200, current_role(description="Updated"))

    result = run(module, client)

    assert result["changed"] is True
    payload = client.roles.update.call_args.args[1]
    assert payload["description"] == "Updated"
    assert payload["elasticsearch"] == current_role()["elasticsearch"]
    assert payload["kibana"] == current_role()["kibana"]
    assert payload["metadata"] == current_role()["metadata"]


def test_replace_clears_omitted_sections_and_check_mode_does_not_write():
    module = FakeModule(
        params(
            description=None,
            elasticsearch=None,
            kibana=None,
            metadata=None,
            transient_metadata=None,
            replace=True,
        ),
        check_mode=True,
        diff=True,
    )
    client = client_with_service()
    client.roles.get.return_value = (200, current_role())

    result = run(module, client)

    assert result["changed"] is True
    assert result["role"]["elasticsearch"] == {}
    assert result["role"]["kibana"] == []
    assert result["role"]["metadata"] == {}
    client.roles.update.assert_not_called()


def test_delete_check_mode_and_repeated_delete():
    module = FakeModule(params(state="absent"), check_mode=True)
    client = client_with_service()
    client.roles.get.return_value = (200, current_role())

    result = run(module, client)
    assert result["changed"] is True
    client.roles.delete.assert_not_called()

    missing = client_with_service()
    missing.roles.get.return_value = (404, {})
    result = run(FakeModule(params(state="absent")), missing)
    assert result["changed"] is False


def test_reserved_roles_cannot_be_modified_or_deleted():
    reserved = current_role(metadata={"_reserved": True})
    for state in ("present", "absent"):
        module = FakeModule(
            params(
                state=state,
                description="different" if state == "present" else None,
            )
        )
        client = client_with_service()
        client.roles.get.return_value = (200, reserved)
        with pytest.raises(ModuleFailure, match="reserved"):
            role.run_module(module, client)
        client.roles.update.assert_not_called()
        client.roles.delete.assert_not_called()


def test_transient_metadata_is_server_managed():
    module = FakeModule(params(transient_metadata={"enabled": False}))
    client = client_with_service()
    client.roles.get.return_value = (200, current_role())
    with pytest.raises(ModuleFailure, match="server-managed"):
        role.run_module(module, client)
    client.roles.update.assert_not_called()


def test_failures_and_response_fields_are_sanitized():
    module = FakeModule(params())
    client = client_with_service()
    client.roles.get.return_value = (
        403,
        {"message": "denied", "metadata": {"private_value": "secret"}},
    )
    with pytest.raises(ModuleFailure) as failure:
        role.run_module(module, client)
    assert "read failed" in failure.value.result["msg"]
    assert failure.value.result["response"]["metadata"]["private_value"] == kibana.REDACTED


def test_malformed_create_response_fails_with_context():
    module = FakeModule(params())
    client = client_with_service()
    client.roles.get.return_value = (404, {})
    client.roles.create.return_value = (200, {"description": "missing name"})
    with pytest.raises(ModuleFailure, match="malformed"):
        role.run_module(module, client)
