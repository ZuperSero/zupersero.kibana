# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest.mock import Mock, call

import pytest

from ansible_collections.zupersero.kibana.plugins.module_utils.kibana_services.saved_object import (
    SavedObjectService,
)


def test_saved_object_service_scopes_and_quotes_every_operation():
    client = Mock()
    client.space_path.side_effect = lambda path: f"/s/operations{path}"
    client.request.side_effect = [
        (200, {"id": "object / one"}),
        (200, {"id": "object / one"}),
        (200, {"id": "object / one"}),
        (204, None),
    ]
    service = SavedObjectService(client)
    sensitive_fields = ["attributes.private_value"]
    payload = {"attributes": {"title": "Logs"}}
    expected_path = "/s/operations/api/saved_objects/index%2Fpattern/object%20%2F%20one"

    service.get("index/pattern", "object / one", sensitive_fields)
    service.create("index/pattern", "object / one", payload, sensitive_fields)
    service.update("index/pattern", "object / one", payload, sensitive_fields)
    service.delete(
        "index/pattern",
        "object / one",
        force=True,
        sensitive_fields=sensitive_fields,
    )

    assert client.space_path.call_args_list == [
        call("/api/saved_objects/index%2Fpattern/object%20%2F%20one"),
        call("/api/saved_objects/index%2Fpattern/object%20%2F%20one"),
        call("/api/saved_objects/index%2Fpattern/object%20%2F%20one"),
        call("/api/saved_objects/index%2Fpattern/object%20%2F%20one"),
    ]
    assert client.request.call_args_list == [
        call("GET", expected_path, sensitive_fields=sensitive_fields),
        call(
            "POST",
            expected_path,
            data=payload,
            sensitive_fields=sensitive_fields,
        ),
        call(
            "PUT",
            expected_path,
            data=payload,
            sensitive_fields=sensitive_fields,
        ),
        call(
            "DELETE",
            expected_path,
            query={"force": "true"},
            sensitive_fields=sensitive_fields,
        ),
    ]


def test_saved_object_delete_omits_force_query_by_default():
    client = Mock()
    client.space_path.side_effect = lambda path: path
    service = SavedObjectService(client)

    service.delete("dashboard", "example")

    client.request.assert_called_once_with(
        "DELETE",
        "/api/saved_objects/dashboard/example",
        query=None,
        sensitive_fields=None,
    )


def test_saved_object_export_uses_space_scoped_supported_api():
    client = Mock()
    client.space_path.return_value = (
        "/s/operations/api/saved_objects/_export"
    )
    service = SavedObjectService(client)
    payload = {
        "objects": [{"type": "dashboard", "id": "object / one"}],
        "includeReferencesDeep": True,
    }

    service.export(payload, sensitive_fields=["attributes.pin"])

    client.space_path.assert_called_once_with("/api/saved_objects/_export")
    client.request.assert_called_once_with(
        "POST",
        "/s/operations/api/saved_objects/_export",
        data=payload,
        sensitive_fields=["attributes.pin"],
        deserialize_json=False,
        sanitize_success_response=False,
    )


def test_saved_object_export_and_import_accept_explicit_space_overrides():
    client = Mock()
    client.space_path.side_effect = (
        lambda path, space_id=None: f"/s/{space_id}{path}"
    )
    service = SavedObjectService(client)
    content = '{"type":"dashboard","id":"one"}\n'

    service.export(
        {"objects": [{"type": "dashboard", "id": "one"}]},
        space_id="source",
    )
    service.import_objects(content, space_id="target")

    assert client.space_path.call_args_list == [
        call("/api/saved_objects/_export", space_id="source"),
        call("/api/saved_objects/_import", space_id="target"),
    ]
    assert client.request.call_args_list[0].args[1] == (
        "/s/source/api/saved_objects/_export"
    )
    assert client.request.call_args_list[1].args[1] == (
        "/s/target/api/saved_objects/_import"
    )


def test_saved_object_import_builds_binary_multipart_without_changing_ndjson(
    monkeypatch,
):
    client = Mock()
    client.space_path.return_value = (
        "/s/operations/api/saved_objects/_import"
    )
    service = SavedObjectService(client)
    content = (
        '{"type":"dashboard","id":"object / one",'
        '"attributes":{"title":"Café"}}\n'
    )
    monkeypatch.setattr(
        "ansible_collections.zupersero.kibana.plugins.module_utils."
        "kibana_services.saved_object.secrets.token_hex",
        lambda _length: "fixedboundary",
    )

    service.import_objects(
        content,
        overwrite=True,
        compatibility_mode=True,
        sensitive_fields=["attributes.pin"],
    )

    client.space_path.assert_called_once_with("/api/saved_objects/_import")
    request = client.request.call_args
    assert request.args == (
        "POST",
        "/s/operations/api/saved_objects/_import",
    )
    assert request.kwargs["query"] == {
        "overwrite": "true",
        "compatibilityMode": "true",
    }
    assert request.kwargs["serialize_json"] is False
    assert request.kwargs["headers"] == {
        "Content-Type": "multipart/form-data; boundary=ansible-fixedboundary"
    }
    body = request.kwargs["data"]
    assert isinstance(body, bytes)
    assert content.encode("utf-8") in body
    assert b'filename="saved_objects.ndjson"' in body
    assert body.endswith(b"--ansible-fixedboundary--\r\n")


@pytest.mark.parametrize(
    "content",
    [
        "",
        " \n",
        '{"type":\n',
        "[]\n",
    ],
)
def test_saved_object_import_rejects_empty_or_malformed_ndjson(content):
    service = SavedObjectService(Mock())

    with pytest.raises(ValueError, match="NDJSON"):
        service.import_objects(content)


def test_saved_object_import_omits_false_query_options():
    client = Mock()
    client.space_path.side_effect = lambda path: path
    service = SavedObjectService(client)

    service.import_objects('{"type":"dashboard","id":"one"}\n')

    assert client.request.call_args.kwargs["query"] is None
