# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest.mock import Mock

from ansible_collections.zupersero.kibana.plugins.module_utils.kibana_services.role import (
    RoleService,
)


def test_role_paths_quote_names_and_support_crud():
    client = Mock()
    service = RoleService(client)
    service.get("role with/slash")
    service.create("role with/slash", {"description": "test"})
    service.update("role with/slash", {"description": "test"})
    service.delete("role with/slash")

    assert client.get.call_args.args[0] == "api/security/role/role%20with%2Fslash"
    assert client.put.call_count == 2
    assert client.put.call_args.args[0] == "api/security/role/role%20with%2Fslash"
    assert client.delete.call_args.args[0] == "api/security/role/role%20with%2Fslash"
