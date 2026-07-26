# Copyright (c) 2026, zupersero
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json

import pytest

from ansible_collections.zupersero.kibana.plugins.module_utils import kibana


class ModuleFailure(Exception):
    def __init__(self, result):
        super().__init__(result["msg"])
        self.result = result


class FakeModule:
    def __init__(self, **overrides):
        self.params = {
            "url": "https://first.example.test",
            "urls": None,
            "username": None,
            "password": None,
            "api_key": None,
            "bearer_token": None,
            "headers": None,
            "space": "default",
            "validate_certs": True,
            "ca_path": None,
            "ca_data": None,
            "client_cert": None,
            "client_key": None,
            "certificate_fingerprint": None,
            "timeout": 30,
            "retries": 0,
            "retry_pause": 0,
            "retry_status_codes": kibana.DEFAULT_RETRY_STATUS_CODES,
            "retry_mutating_requests": False,
            "url_username": None,
            "url_password": None,
        }
        self.params.update(overrides)
        self.tmpdir = None

    def fail_json(self, **result):
        raise ModuleFailure(result)


class FakeResponse:
    def __init__(self, value):
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        self.value = value.encode() if isinstance(value, str) else value

    def read(self):
        return self.value


def test_argument_spec_marks_credentials_and_headers_no_log():
    spec = kibana.kibana_argument_spec()

    assert spec["password"]["no_log"] is True
    assert spec["api_key"]["no_log"] is True
    assert spec["bearer_token"]["no_log"] is True
    assert spec["headers"]["no_log"] is True
    assert spec["client_key"]["no_log"] is True
    assert spec["headers"]["default"] == {}
    assert spec["retry_status_codes"]["default"] == [
        408,
        429,
        *range(500, 600),
    ]
    assert spec["retry_mutating_requests"]["default"] is False
    assert "state" in spec
    assert "state" not in kibana.kibana_argument_spec(include_state=False)


def test_connection_constraints_cover_auth_tls_and_endpoint_conflicts():
    assert ["username", "password"] in kibana.kibana_required_together()
    conflicts = kibana.kibana_mutually_exclusive()

    assert ["url", "urls"] in conflicts
    assert ["ca_path", "ca_data"] in conflicts
    assert ["username", "api_key", "bearer_token", "url_username"] in conflicts


def test_query_encoding_is_deterministic_and_supports_repeated_values():
    assert kibana.add_query(
        "/api/items?existing=yes",
        {"z": "last", "a": ["one", "two"], "ignored": None},
    ) == "/api/items?existing=yes&a=one&a=two&z=last"


def test_comparison_projects_server_fields_and_sanitizes_diff():
    current = {
        "attributes": {
            "name": "example",
            "password": "server-secret",
            "tags": ["b", "a"],
            "server_owned": True,
        },
        "updated_at": "later",
    }
    desired = {
        "attributes": {
            "name": "example",
            "password": "server-secret",
            "tags": ["a", "b"],
        }
    }

    changed, diff = kibana.comparison_diff(
        current,
        desired,
        sensitive_fields=["attributes.password"],
        unordered_lists=True,
    )

    assert changed is False
    assert "server_owned" not in diff["before"]["attributes"]
    assert diff["before"]["attributes"]["password"] == kibana.REDACTED
    assert diff["after"]["attributes"]["password"] == kibana.REDACTED


def test_sanitize_matches_extended_secret_names_and_list_paths():
    value = {
        "client_secret": "one",
        "access_token": "two",
        "private_key": "three",
        "items": [{"pin": "1234"}, {"pin": "5678"}],
    }

    result = kibana.sanitize(value, sensitive_fields=["items.pin"])

    assert result["client_secret"] == kibana.REDACTED
    assert result["access_token"] == kibana.REDACTED
    assert result["private_key"] == kibana.REDACTED
    assert [item["pin"] for item in result["items"]] == [
        kibana.REDACTED,
        kibana.REDACTED,
    ]


@pytest.mark.parametrize(
    ("parameters", "expected"),
    [
        ({"api_key": "encoded"}, "ApiKey encoded"),
        ({"bearer_token": "opaque"}, "Bearer opaque"),
        (
            {"username": "elastic", "password": "changeme"},
            "Basic ZWxhc3RpYzpjaGFuZ2VtZQ==",
        ),
    ],
)
def test_authentication_headers(monkeypatch, parameters, expected):
    calls = []

    def fake_fetch(_module, url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse({"ok": True}), {"status": 200}

    monkeypatch.setattr(kibana, "fetch_url", fake_fetch)
    client = kibana.KibanaClient(FakeModule(**parameters))

    status, response = client.get("/api/status")

    assert status == 200
    assert response == {"ok": True}
    assert calls[0][1]["headers"]["Authorization"] == expected
    assert calls[0][1]["headers"]["Accept"] == "application/json"
    assert calls[0][1]["headers"]["Content-Type"] == "application/json"
    assert calls[0][1]["headers"]["kbn-xsrf"] == "true"


def test_failover_retries_next_endpoint_and_sanitizes_errors(monkeypatch):
    calls = []

    def fake_fetch(_module, url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            return None, {
                "status": 503,
                "msg": "failed with secret-header",
                "body": b'{"message":"secret-header unavailable"}',
            }
        return FakeResponse({"ok": True}), {"status": 200}

    monkeypatch.setattr(kibana, "fetch_url", fake_fetch)
    client = kibana.KibanaClient(
        FakeModule(
            url=None,
            urls=["https://first.example.test", "https://second.example.test"],
            headers={"X-Secret": "secret-header"},
            retries=1,
        )
    )

    assert client.get("/api/status") == (200, {"ok": True})
    assert calls == [
        "https://first.example.test/api/status",
        "https://second.example.test/api/status",
    ]
    assert client.get("/api/status") == (200, {"ok": True})
    assert calls[-1] == "https://second.example.test/api/status"


def test_configured_retry_status_code_triggers_failover(monkeypatch):
    calls = []

    def fake_fetch(_module, url, **_kwargs):
        calls.append(url)
        if len(calls) == 1:
            return None, {"status": 404, "msg": "try another endpoint"}
        return FakeResponse({"ok": True}), {"status": 200}

    monkeypatch.setattr(kibana, "fetch_url", fake_fetch)
    client = kibana.KibanaClient(
        FakeModule(
            url=None,
            urls=["https://first.example.test", "https://second.example.test"],
            retries=1,
            retry_status_codes=[404],
        )
    )

    assert client.get("/api/status") == (200, {"ok": True})
    assert calls == [
        "https://first.example.test/api/status",
        "https://second.example.test/api/status",
    ]


def test_404_and_malformed_success_responses_are_preserved(monkeypatch):
    responses = iter(
        [
            (None, {"status": 404, "body": b'{"message":"missing"}'}),
            (FakeResponse("not-json"), {"status": 200}),
        ]
    )
    monkeypatch.setattr(kibana, "fetch_url", lambda *_args, **_kwargs: next(responses))
    client = kibana.KibanaClient(FakeModule())

    assert client.get("/api/missing") == (404, {"message": "missing"})
    assert client.get("/api/text") == (200, "not-json")


@pytest.mark.parametrize(
    "path",
    [
        "https://attacker.example.test/api/status",
        "//attacker.example.test/api/status",
        r"\\attacker.example.test\api\status",
    ],
)
def test_absolute_and_cross_origin_paths_are_rejected_before_headers(
    monkeypatch, path
):
    client = kibana.KibanaClient(
        FakeModule(
            api_key="must-not-leak",
            headers={"X-Secret": "must-not-leak"},
        )
    )
    monkeypatch.setattr(
        client,
        "_request_headers",
        lambda *_args, **_kwargs: pytest.fail("headers were constructed"),
    )
    monkeypatch.setattr(
        kibana,
        "fetch_url",
        lambda *_args, **_kwargs: pytest.fail("request was sent"),
    )

    with pytest.raises(ModuleFailure, match="relative"):
        client.get(path)


def test_space_scoping_cannot_hide_an_absolute_path():
    client = kibana.KibanaClient(
        FakeModule(
            space="restricted",
            api_key="must-not-leak",
        )
    )

    with pytest.raises(ModuleFailure, match="relative"):
        client.space_path("https://attacker.example.test/api/status")


def test_fingerprint_rejects_http_endpoint():
    with pytest.raises(ModuleFailure, match="HTTPS"):
        kibana.KibanaClient(
            FakeModule(
                url="http://kibana.example.test",
                certificate_fingerprint="a" * 64,
            )
        )


def test_fingerprint_preflight_happens_before_sensitive_headers(monkeypatch):
    events = []
    client = kibana.KibanaClient(
        FakeModule(
            api_key="must-not-leak",
            headers={"X-Secret": "must-not-leak"},
            certificate_fingerprint="a" * 64,
        )
    )
    monkeypatch.setattr(
        client,
        "_preflight_fingerprint",
        lambda endpoint: events.append(("preflight", endpoint)),
    )
    original_headers = client._request_headers

    def record_headers(extra_headers=None):
        events.append(("headers", None))
        return original_headers(extra_headers)

    monkeypatch.setattr(client, "_request_headers", record_headers)
    monkeypatch.setattr(
        kibana,
        "fetch_url",
        lambda *_args, **_kwargs: (
            FakeResponse({"ok": True}),
            {"status": 200},
        ),
    )

    assert client.get("/api/status") == (200, {"ok": True})
    assert [event[0] for event in events] == ["preflight", "headers"]


def test_mutating_requests_are_not_retried_by_default(monkeypatch):
    calls = []

    def fake_fetch(_module, url, **_kwargs):
        calls.append(url)
        return None, {"status": 503, "msg": "unavailable"}

    monkeypatch.setattr(kibana, "fetch_url", fake_fetch)
    client = kibana.KibanaClient(
        FakeModule(
            url=None,
            urls=["https://first.example.test", "https://second.example.test"],
            retries=3,
        )
    )

    with pytest.raises(ModuleFailure, match="after 1 attempts"):
        client.post("/api/action", data={"run": True})
    assert calls == ["https://first.example.test/api/action"]


def test_mutating_request_retry_requires_explicit_opt_in(monkeypatch):
    calls = []

    def fake_fetch(_module, url, **_kwargs):
        calls.append(url)
        if len(calls) == 1:
            return None, {"status": 503, "msg": "unavailable"}
        return FakeResponse({"ok": True}), {"status": 200}

    monkeypatch.setattr(kibana, "fetch_url", fake_fetch)
    client = kibana.KibanaClient(
        FakeModule(
            url=None,
            urls=["https://first.example.test", "https://second.example.test"],
            retries=1,
            retry_mutating_requests=True,
        )
    )

    assert client.post("/api/action", data={"run": True}) == (200, {"ok": True})
    assert calls == [
        "https://first.example.test/api/action",
        "https://second.example.test/api/action",
    ]


def test_pagination_collects_pages(monkeypatch):
    client = kibana.KibanaClient(FakeModule())
    responses = iter(
        [
            (200, {"items": [{"id": 1}, {"id": 2}], "total": 3}),
            (200, {"items": [{"id": 3}], "total": 3}),
        ]
    )
    calls = []

    def fake_request(method, path, query=None, **_kwargs):
        calls.append((method, path, query))
        return next(responses)

    monkeypatch.setattr(client, "request", fake_request)

    status, items, response = client.paginate(
        "/api/items", "items", page_size=2, max_pages=5
    )

    assert status == 200
    assert items == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert response["total"] == 3
    assert calls[1][2] == {"page": 2, "per_page": 2}


def test_exhausted_retry_redacts_configured_error_fields(monkeypatch):
    monkeypatch.setattr(
        kibana,
        "fetch_url",
        lambda *_args, **_kwargs: (
            None,
            {
                "status": 503,
                "msg": "unavailable",
                "body": b'{"attributes":{"pin":"must-not-leak"}}',
            },
        ),
    )
    client = kibana.KibanaClient(FakeModule())

    with pytest.raises(ModuleFailure) as failure:
        client.request(
            "GET",
            "/api/items",
            sensitive_fields=["attributes.pin"],
        )

    assert (
        failure.value.result["response"]["attributes"]["pin"]
        == kibana.REDACTED
    )


def test_pagination_rejects_non_list_response_path(monkeypatch):
    client = kibana.KibanaClient(FakeModule())
    monkeypatch.setattr(
        client,
        "request",
        lambda *_args, **_kwargs: (200, {"items": {"id": 1}}),
    )

    with pytest.raises(ModuleFailure, match="did not contain a list"):
        client.paginate("/api/items", "items", page_size=2, max_pages=2)


def test_pagination_rejects_missing_response_path(monkeypatch):
    client = kibana.KibanaClient(FakeModule())
    monkeypatch.setattr(
        client,
        "request",
        lambda *_args, **_kwargs: (200, {"different": []}),
    )

    with pytest.raises(ModuleFailure, match="did not contain a list"):
        client.paginate("/api/items", "items", page_size=2, max_pages=2)


def test_pagination_fails_when_max_pages_truncates_results(monkeypatch):
    client = kibana.KibanaClient(FakeModule())
    monkeypatch.setattr(
        client,
        "request",
        lambda *_args, **_kwargs: (
            200,
            {"items": [{"id": 1}, {"id": 2}], "total": 3},
        ),
    )

    with pytest.raises(ModuleFailure, match="reached max_pages=1"):
        client.paginate("/api/items", "items", page_size=2, max_pages=1)


def test_version_and_feature_comparison(monkeypatch):
    client = object.__new__(kibana.KibanaClient)
    client._version = None
    monkeypatch.setattr(
        client,
        "get",
        lambda _path: (200, {"version": {"number": "9.2.0-SNAPSHOT"}}),
    )

    assert client.version() == "9.2.0-SNAPSHOT"
    assert client.supports_version("9.1.0") is True
    assert client.supports_version("10.0.0") is False
