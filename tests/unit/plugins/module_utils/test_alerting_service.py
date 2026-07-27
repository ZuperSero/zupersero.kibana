# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest.mock import Mock, call

from ansible_collections.zupersero.kibana.plugins.module_utils.kibana_services.alerting import (
    AlertingRuleService,
    MaintenanceWindowService,
)


def test_alerting_rule_service_scopes_quotes_and_dispatches_operations():
    client = Mock()
    client.space_path.side_effect = lambda path: f"/s/operations{path}"
    service = AlertingRuleService(client)
    payload = {"name": "Rule", "schedule": {"interval": "5m"}}
    sensitive = ["params.private"]
    expected = "/s/operations/api/alerting/rule/rule%20%2F%20one"

    service.get("rule / one", sensitive)
    service.create("rule / one", payload, sensitive)
    service.update("rule / one", payload, sensitive)
    service.set_enabled("rule / one", True, sensitive)
    service.set_enabled("rule / one", False, sensitive)
    service.delete("rule / one", sensitive)
    service.rule_types(sensitive)

    assert client.request.call_args_list == [
        call("GET", expected, sensitive_fields=sensitive),
        call("POST", expected, data=payload, sensitive_fields=sensitive),
        call("PUT", expected, data=payload, sensitive_fields=sensitive),
        call("POST", f"{expected}/_enable", data=None, sensitive_fields=sensitive),
        call("POST", f"{expected}/_disable", data={}, sensitive_fields=sensitive),
        call("DELETE", expected, sensitive_fields=sensitive),
        call(
            "GET",
            "/s/operations/api/alerting/rule_types",
            sensitive_fields=sensitive,
        ),
    ]


def test_maintenance_window_service_uses_supported_space_aware_routes():
    client = Mock()
    client.space_path.return_value = "/s/operations/api/maintenance_window"
    service = MaintenanceWindowService(client)
    payload = {"title": "Window", "schedule": {"custom": {}}}
    sensitive = ["scope.alerting.query.kql"]
    expected = "/s/operations/api/maintenance_window/window%20%2F%20one"

    service.find("Window / one", sensitive)
    service.get("window / one", sensitive)
    service.create(payload, sensitive)
    service.update("window / one", payload, sensitive)
    service.archive("window / one", sensitive)
    service.delete("window / one", sensitive)

    assert client.request.call_args_list == [
        call(
            "GET",
            "/s/operations/api/maintenance_window/_find",
            query={"title": "Window / one", "page": 1, "per_page": 100},
            sensitive_fields=sensitive,
        ),
        call("GET", expected, sensitive_fields=sensitive),
        call(
            "POST",
            "/s/operations/api/maintenance_window",
            data=payload,
            sensitive_fields=sensitive,
        ),
        call("PATCH", expected, data=payload, sensitive_fields=sensitive),
        call("POST", f"{expected}/_archive", sensitive_fields=sensitive),
        call("DELETE", expected, sensitive_fields=sensitive),
    ]
