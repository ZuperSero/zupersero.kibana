from unittest.mock import Mock

import pytest

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana
from ansible_collections.zupersero.kibana.plugins.modules import (
    agent_download_source,
    enrollment_token,
    fleet_output,
    fleet_proxy,
    fleet_server_host,
)
from ansible_collections.zupersero.kibana.plugins.module_utils import fleet_resource


class ExitResult(Exception):
    def __init__(self, result):
        self.result = result


class FakeModule:
    def __init__(self, params, check_mode=False, diff=False):
        self.params = params
        self.check_mode = check_mode
        self._diff = diff

    def exit_json(self, **result):
        raise ExitResult(result)

    def fail_json(self, **result):
        raise RuntimeError(result["msg"])


def test_proxy_create_check_mode_and_idempotence():
    params = {
        "id": None, "name": "egress", "proxy_url": "http://proxy:8080",
        "state": "present", "sensitive_fields": [], "replace": False,
    }
    module = FakeModule(params, check_mode=True, diff=True)
    client = Mock()
    client.fleet_proxies = Mock()
    client.fleet_proxies.list.return_value = (200, {"items": []})
    with pytest.raises(ExitResult) as result:
        fleet_resource.run_module(module, client, fleet_proxy.CONFIG)
    assert result.value.result["changed"] is True
    assert result.value.result["fleet_proxy"]["name"] == "egress"
    client.fleet_proxies.create.assert_not_called()


def test_enrollment_token_redacts_api_key():
    params = {
        "id": None, "name": "agent", "policy_id": "policy",
        "expiration": None, "state": "present", "sensitive_fields": [],
        "replace": False,
    }
    module = FakeModule(params)
    client = Mock()
    client.enrollment_tokens = Mock()
    client.enrollment_tokens.list.return_value = (200, {"items": []})
    client.enrollment_tokens.create.return_value = (
        200,
        {"item": {"id": "id", "name": "agent", "api_key": "secret-token", "policy_id": "policy"}},
    )
    with pytest.raises(ExitResult) as result:
        fleet_resource.run_module(module, client, enrollment_token.CONFIG)
    assert result.value.result["enrollment_token"]["api_key"] == kibana.REDACTED


@pytest.mark.parametrize("module", [fleet_output, fleet_proxy, fleet_server_host, agent_download_source, enrollment_token])
def test_public_modules_have_common_state_argument(module):
    spec = module.__dict__[f"{module.__name__.split('.')[-1]}_argument_spec"]()
    assert spec["state"]["choices"] == ["present", "absent"]
    assert spec["sensitive_fields"].get("default") == []
