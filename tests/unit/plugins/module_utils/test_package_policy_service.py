# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest.mock import Mock

from ansible_collections.zupersero.kibana.plugins.module_utils.kibana_services.package_policy import (
    PackagePolicyService,
)


def test_service_quotes_ids_for_get_update_and_delete():
    client = Mock()
    service = PackagePolicyService(client)

    service.get("policy/with spaces")
    service.update("policy/with spaces", {"name": "example"})
    service.delete("policy/with spaces", force=True)

    assert client.get.call_args.args[0] == "api/fleet/package_policies/policy%2Fwith%20spaces"
    assert client.put.call_args.args[0] == "api/fleet/package_policies/policy%2Fwith%20spaces"
    assert client.delete.call_args.args[0].endswith("?force=true")


def test_service_uses_fleet_package_policy_endpoints():
    client = Mock()
    service = PackagePolicyService(client)

    service.list(page=2, per_page=25)
    service.create({"name": "example"})

    assert client.get.call_args.args[0] == "api/fleet/package_policies?page=2&perPage=25"
    assert client.post.call_args.args[0] == "api/fleet/package_policies"
