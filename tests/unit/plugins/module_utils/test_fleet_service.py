from unittest.mock import Mock

from ansible_collections.zupersero.kibana.plugins.module_utils.kibana_services.fleet import (
    AgentDownloadSourceService,
    EnrollmentTokenService,
    FleetOutputService,
    FleetProxyService,
    FleetServerHostService,
)


def test_fleet_services_use_space_paths_and_quote_ids():
    client = Mock()
    client.space_path.side_effect = lambda value: f"/s/dev/{value}"
    for service, endpoint in (
        (FleetOutputService(client), "outputs"),
        (FleetProxyService(client), "proxies"),
        (FleetServerHostService(client), "fleet_server_hosts"),
        (AgentDownloadSourceService(client), "agent_download_sources"),
    ):
        service.get("id/with space")
        assert client.get.call_args.args[0] == f"/s/dev/api/fleet/{endpoint}/id%2Fwith%20space"


def test_enrollment_service_uses_expected_actions():
    client = Mock()
    client.space_path.side_effect = lambda value: value
    service = EnrollmentTokenService(client)
    service.create({"policy_id": "policy"})
    service.delete("key/id")
    assert client.post.call_args.args[0] == "api/fleet/enrollment_api_keys"
    assert client.delete.call_args.args[0] == "api/fleet/enrollment_api_keys/key%2Fid"
