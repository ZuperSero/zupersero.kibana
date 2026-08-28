# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest.mock import Mock

import pytest

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana
from ansible_collections.zupersero.kibana.plugins.modules import (
    kibana_info,
    kibana_object,
    kibana_request,
)


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


def object_params(**overrides):
    params = {
        "path": "/api/object/{id}",
        "id": "managed/object",
        "payload": {"attributes": {"name": "managed", "pin": "5678"}},
        "query": {},
        "create_path": None,
        "get_method": "GET",
        "create_method": "PUT",
        "update_method": "PUT",
        "delete_method": "DELETE",
        "get_success_codes": [200],
        "create_success_codes": [200, 201, 202],
        "update_success_codes": [200, 201, 202],
        "delete_success_codes": [200, 202, 204],
        "not_found_codes": [404],
        "response_path": None,
        "compare_fields": [],
        "ignore_fields": [],
        "sensitive_fields": ["attributes.pin"],
        "unordered_lists": False,
        "state": "present",
    }
    params.update(overrides)
    return params


def client_with_responses(*responses):
    client = Mock()
    client.space_path.side_effect = lambda path: path
    client.request.side_effect = responses
    return client


def test_object_redacts_sensitive_fields_on_unchanged_return():
    current = {
        "attributes": {
            "name": "managed",
            "pin": "5678",
            "client_secret": "server-secret",
        }
    }
    module = FakeModule(object_params())
    client = client_with_responses((200, current))

    with pytest.raises(ModuleExit) as exit_result:
        kibana_object.run_module(module, client)

    result = exit_result.value.result
    assert result["changed"] is False
    assert result["object"]["attributes"]["pin"] == kibana.REDACTED
    assert result["object"]["attributes"]["client_secret"] == kibana.REDACTED


def test_object_redacts_check_mode_object_and_every_diff_side():
    current = {"attributes": {"name": "old", "pin": "1234"}}
    module = FakeModule(object_params(), check_mode=True, diff=True)
    client = client_with_responses((200, current))

    with pytest.raises(ModuleExit) as exit_result:
        kibana_object.run_module(module, client)

    result = exit_result.value.result
    assert result["changed"] is True
    assert result["object"]["attributes"]["pin"] == kibana.REDACTED
    assert result["diff"]["before"]["attributes"]["pin"] == kibana.REDACTED
    assert result["diff"]["after"]["attributes"]["pin"] == kibana.REDACTED


def test_object_redacts_mutation_response():
    module = FakeModule(object_params())
    client = client_with_responses(
        (404, {"message": "missing"}),
        (
            201,
            {
                "attributes": {
                    "name": "managed",
                    "pin": "5678",
                    "access_token": "returned-token",
                }
            },
        ),
    )

    with pytest.raises(ModuleExit) as exit_result:
        kibana_object.run_module(module, client)

    attributes = exit_result.value.result["object"]["attributes"]
    assert attributes["pin"] == kibana.REDACTED
    assert attributes["access_token"] == kibana.REDACTED


def test_object_failure_redacts_configured_and_automatic_secrets():
    module = FakeModule(object_params())
    client = client_with_responses(
        (
            401,
            {
                "attributes": {"pin": "1234"},
                "private_key": "must-not-leak",
            },
        )
    )

    with pytest.raises(ModuleFailure) as failure:
        kibana_object.run_module(module, client)

    response = failure.value.result["response"]
    assert response["attributes"]["pin"] == kibana.REDACTED
    assert response["private_key"] == kibana.REDACTED


def test_request_redacts_sensitive_fields_from_output():
    module = FakeModule(
        {
            "path": "/api/status",
            "method": "GET",
            "body": None,
            "query": {},
            "success_codes": [200],
            "response_path": None,
            "sensitive_fields": ["attributes.pin"],
        }
    )
    client = client_with_responses(
        (
            200,
            {
                "attributes": {"pin": "1234"},
                "access_token": "must-not-leak",
            },
        )
    )

    with pytest.raises(ModuleExit) as exit_result:
        kibana_request.run_module(module, client)

    response = exit_result.value.result["response"]
    assert response["attributes"]["pin"] == kibana.REDACTED
    assert response["access_token"] == kibana.REDACTED


def test_info_redacts_objects_and_raw_response():
    module = FakeModule(
        {
            "path": "/api/items",
            "query": {},
            "response_path": "items",
            "paginate": False,
            "page_parameter": "page",
            "per_page_parameter": "per_page",
            "page_size": 100,
            "max_pages": 100,
            "success_codes": [200],
            "sensitive_fields": ["pin"],
        }
    )
    client = client_with_responses(
        (
            200,
            {
                "items": [
                    {"id": "one", "pin": "1234", "client_secret": "secret"}
                ]
            },
        )
    )

    with pytest.raises(ModuleExit) as exit_result:
        kibana_info.run_module(module, client)

    result = exit_result.value.result
    assert result["objects"][0]["pin"] == kibana.REDACTED
    assert result["objects"][0]["client_secret"] == kibana.REDACTED
    assert result["response"]["items"][0]["pin"] == kibana.REDACTED
    assert result["response"]["items"][0]["client_secret"] == kibana.REDACTED
