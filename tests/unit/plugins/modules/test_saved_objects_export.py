# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest.mock import Mock

import pytest

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana
from ansible_collections.zupersero.kibana.plugins.modules import (
    saved_objects_export,
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
    def __init__(self, params, check_mode=False):
        self.params = params
        self.check_mode = check_mode

    def exit_json(self, **result):
        raise ModuleExit(result)

    def fail_json(self, **result):
        raise ModuleFailure(result)


def module_params(**overrides):
    params = {
        "types": None,
        "objects": [{"type": "dashboard", "id": "object / one"}],
        "include_references_deep": True,
        "exclude_export_details": False,
        "search": None,
        "has_reference": None,
        "sensitive_fields": ["attributes.pin"],
    }
    params.update(overrides)
    return params


def client_with_service():
    client = Mock()
    client.saved_objects = Mock()
    return client


def run_and_exit(module, client):
    with pytest.raises(ModuleExit) as exit_result:
        saved_objects_export.run_module(module, client)
    return exit_result.value.result


def test_argument_spec_and_selection_contract():
    spec = saved_objects_export.saved_objects_export_argument_spec()

    assert spec["types"]["elements"] == "str"
    assert spec["objects"]["options"]["type"]["required"] is True
    assert spec["objects"]["options"]["id"]["required"] is True
    assert spec["has_reference"]["options"]["id"]["required"] is True
    assert spec["include_references_deep"]["default"] is False
    assert spec["exclude_export_details"]["default"] is False
    assert "state" not in spec


def test_build_export_payload_translates_names_and_omits_unsupplied_values():
    payload = saved_objects_export.build_export_payload(
        module_params(
            objects=None,
            types=["dashboard", "visualization"],
            search='title: "Application"',
            has_reference=[{"type": "index-pattern", "id": "logs / one"}],
        )
    )

    assert payload == {
        "type": ["dashboard", "visualization"],
        "includeReferencesDeep": True,
        "excludeExportDetails": False,
        "search": 'title: "Application"',
        "hasReference": [{"type": "index-pattern", "id": "logs / one"}],
    }


def test_export_is_read_only_in_check_mode_and_preserves_opaque_ndjson():
    content = (
        '{"type":"dashboard","id":"object / one",'
        '"attributes":{"title":"Café","pin":"1234"}}\n'
        '{"exportedCount":1,"missingRefCount":0,"missingReferences":[]}\n'
    )
    module = FakeModule(module_params(), check_mode=True)
    client = client_with_service()
    client.saved_objects.export.return_value = (200, content)

    result = run_and_exit(module, client)

    assert result["changed"] is False
    assert result["ndjson"] == content
    assert result["object_count"] == 1
    assert result["objects"][0]["attributes"]["title"] == "Café"
    assert result["objects"][0]["attributes"]["pin"] == kibana.REDACTED
    assert result["export_details"]["exportedCount"] == 1
    client.saved_objects.export.assert_called_once_with(
        {
            "objects": [{"type": "dashboard", "id": "object / one"}],
            "includeReferencesDeep": True,
            "excludeExportDetails": False,
        },
        sensitive_fields=["attributes.pin"],
    )


def test_export_without_details_returns_all_records_as_objects():
    content = '{"type":"dashboard","id":"one","attributes":{}}\n'
    module = FakeModule(module_params(exclude_export_details=True))
    client = client_with_service()
    client.saved_objects.export.return_value = (200, content)

    result = run_and_exit(module, client)

    assert result["export_details"] is None
    assert result["object_count"] == 1
    assert result["objects"][0]["id"] == "one"


@pytest.mark.parametrize(
    ("status", "response", "message"),
    [
        (400, {"message": "bad request"}, "failed with HTTP 400"),
        (200, {"unexpected": "json"}, "malformed non-NDJSON"),
        (200, '{"type":\n', "malformed NDJSON"),
    ],
)
def test_export_api_and_malformed_responses_fail_with_context(
    status,
    response,
    message,
):
    module = FakeModule(module_params())
    client = client_with_service()
    client.saved_objects.export.return_value = (status, response)

    with pytest.raises(ModuleFailure) as failure:
        saved_objects_export.run_module(module, client)

    assert message in failure.value.result["msg"]
    assert failure.value.result["status"] == status
