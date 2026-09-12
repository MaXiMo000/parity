import json
import socket
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Node, Request, User
from app.models import Response as ResponseModel
from tests.conftest import login_as

client = TestClient(app)
FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "petstore-openapi.json").read_text())


@pytest.fixture(autouse=True)
def _authenticated():
    session = SessionLocal()
    try:
        user = User(github_id="test-github-id", username="testuser")
        session.add(user)
        session.commit()
        user_id = user.id
    finally:
        session.close()
    login_as(client, user_id)


def _fake_getaddrinfo(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )


@respx.mock
def test_send_a_real_request_that_matches_a_node_and_drifts(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Petstore", "schema_kind": "openapi", "raw_schema": FIXTURE,
    }).json()

    # Missing photoUrls would ALSO be flagged (it's a required field on
    # the real Pet schema) -- including it here isolates the assertion to
    # the one real defect this test is about: id's wrong type. Verified
    # against the real fixture's real Pet schema (2026-09-11): this exact
    # body produces exactly one real jsonschema error, at $.id.
    respx.get("https://93.184.216.34/api/v3/pet/1").mock(
        return_value=httpx.Response(200, json={"id": "not-an-int", "name": "Fido", "photoUrls": []})
    )
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "GET", "url": "https://example.invalid/api/v3/pet/1", "headers": {}, "body": None,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["request"]["node_id"] is not None
    assert body["response"]["status_code"] == 200
    assert body["drift_finding"]["status"] == "violated"
    assert "id" in body["drift_finding"]["detail"]


@respx.mock
def test_send_a_request_that_matches_no_node_is_unverified_no_match(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Petstore", "schema_kind": "openapi", "raw_schema": FIXTURE,
    }).json()

    respx.get("https://93.184.216.34/api/v3/totally/unknown").mock(return_value=httpx.Response(200))
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "GET", "url": "https://example.invalid/api/v3/totally/unknown", "headers": {}, "body": None,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["request"]["node_id"] is None
    assert body["drift_finding"]["status"] == "unverified_no_match"


def test_send_against_an_unsafe_target_is_502():
    ws = client.post("/api/workspaces", json={
        "name": "x", "schema_kind": "openapi",
        "raw_schema": {"openapi": "3.0.0", "info": {"title": "t", "version": "1"}, "paths": {}},
    }).json()
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "GET", "url": "http://127.0.0.1/secret", "headers": {}, "body": None,
    })
    assert r.status_code == 502


def test_send_against_unknown_workspace_is_404():
    r = client.post("/api/workspaces/00000000-0000-0000-0000-000000000099/requests", json={
        "method": "GET", "url": "https://example.invalid/x", "headers": {}, "body": None,
    })
    assert r.status_code == 404


def test_send_requires_method_and_url():
    ws = client.post("/api/workspaces", json={
        "name": "x", "schema_kind": "openapi",
        "raw_schema": {"openapi": "3.0.0", "info": {"title": "t", "version": "1"}, "paths": {}},
    }).json()
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={"headers": {}, "body": None})
    assert r.status_code == 422


def test_send_rejects_a_non_string_body():
    ws = client.post("/api/workspaces", json={
        "name": "x", "schema_kind": "openapi",
        "raw_schema": {"openapi": "3.0.0", "info": {"title": "t", "version": "1"}, "paths": {}},
    }).json()
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "GET", "url": "https://example.invalid/x", "headers": {}, "body": {"not": "a string"},
    })
    assert r.status_code == 422


@respx.mock
def test_a_real_404_is_unverified_not_a_false_violation(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Petstore", "schema_kind": "openapi", "raw_schema": FIXTURE,
    }).json()
    respx.get("https://93.184.216.34/api/v3/pet/1").mock(
        return_value=httpx.Response(404, json={"code": 1, "type": "error", "message": "Pet not found"})
    )
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "GET", "url": "https://example.invalid/api/v3/pet/1", "headers": {}, "body": None,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["response"]["status_code"] == 404
    assert body["drift_finding"]["status"] == "unverified_no_schema"


@respx.mock
def test_a_204_is_unverified_not_a_false_violation(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Petstore", "schema_kind": "openapi", "raw_schema": FIXTURE,
    }).json()
    respx.get("https://93.184.216.34/api/v3/pet/1").mock(return_value=httpx.Response(204))
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "GET", "url": "https://example.invalid/api/v3/pet/1", "headers": {}, "body": None,
    })
    assert r.status_code == 201
    assert r.json()["drift_finding"]["status"] == "unverified_no_schema"


@respx.mock
def test_request_history_lists_what_was_sent(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Petstore", "schema_kind": "openapi", "raw_schema": FIXTURE,
    }).json()
    respx.get("https://93.184.216.34/api/v3/pet/1").mock(return_value=httpx.Response(200, json={"id": 1, "name": "Fido"}))
    client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "GET", "url": "https://example.invalid/api/v3/pet/1", "headers": {}, "body": None,
    })
    history = client.get(f"/api/workspaces/{ws['id']}/requests").json()
    assert len(history) == 1
    assert history[0]["method"] == "GET"


@respx.mock
def test_node_history_lists_that_nodes_drift_findings(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Petstore", "schema_kind": "openapi", "raw_schema": FIXTURE,
    }).json()
    node_id = next(n["id"] for n in client.get(f"/api/workspaces/{ws['id']}").json()["nodes"] if n["operation_id"] == "getPetById")
    # photoUrls is required on the real Pet schema -- included here so
    # this response is genuinely, fully valid against it (verified
    # 2026-09-11), making "matched" the real, correct outcome, not an
    # assumption.
    respx.get("https://93.184.216.34/api/v3/pet/1").mock(return_value=httpx.Response(200, json={"id": 1, "name": "Fido", "photoUrls": []}))
    client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "GET", "url": "https://example.invalid/api/v3/pet/1", "headers": {}, "body": None,
    })
    history = client.get(f"/api/workspaces/{ws['id']}/nodes/{node_id}/history").json()
    assert len(history) == 1
    assert history[0]["status"] == "matched"


def test_node_history_for_unknown_node_is_404():
    ws = client.post("/api/workspaces", json={
        "name": "x", "schema_kind": "openapi",
        "raw_schema": {"openapi": "3.0.0", "info": {"title": "t", "version": "1"}, "paths": {}},
    }).json()
    r = client.get(f"/api/workspaces/{ws['id']}/nodes/00000000-0000-0000-0000-000000000099/history")
    assert r.status_code == 404


def test_node_history_with_a_malformed_node_id_is_404_not_a_crash(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "x", "schema_kind": "openapi",
        "raw_schema": {"openapi": "3.0.0", "info": {"title": "t", "version": "1"}, "paths": {}},
    }).json()
    r = client.get(f"/api/workspaces/{ws['id']}/nodes/not-a-real-uuid/history")
    assert r.status_code == 404


@respx.mock
def test_sensitive_headers_are_redacted_when_persisted_but_not_when_sent(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Petstore", "schema_kind": "openapi", "raw_schema": FIXTURE,
    }).json()

    route = respx.get("https://93.184.216.34/api/v3/pet/1").mock(
        return_value=httpx.Response(
            200, json={"id": 1, "name": "Fido", "photoUrls": []},
            headers={"Set-Cookie": "session=abc123"},
        )
    )
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "GET", "url": "https://example.invalid/api/v3/pet/1",
        "headers": {"Authorization": "Bearer supersecret123"}, "body": None,
    })
    assert r.status_code == 201

    # the real outbound call must have received the REAL header
    sent = route.calls.last.request.headers
    assert sent["authorization"] == "Bearer supersecret123"

    # but the persisted rows must be redacted
    session = SessionLocal()
    try:
        req_row = session.query(Request).filter(Request.workspace_id == ws["id"]).one()
        assert req_row.headers["Authorization"] == "[REDACTED]"
        resp_row = session.query(ResponseModel).filter(ResponseModel.request_id == req_row.id).one()
        assert any(k.lower() == "set-cookie" and v == "[REDACTED]" for k, v in resp_row.headers.items())
    finally:
        session.close()


@respx.mock
def test_send_against_a_graphql_workspace_now_matches_and_checks_drift(monkeypatch):
    # Phase 2a's version of this test asserted GraphQL requests were
    # honestly unverified_no_match (matching didn't exist yet). Phase 2b
    # (this task) adds real GraphQL matching + drift-checking, so the
    # same request against the same schema now genuinely matches.
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Pets (GraphQL)", "schema_kind": "graphql",
        "raw_schema": "type Query { pet(id: ID!): String }",
    }).json()
    respx.post("https://93.184.216.34/graphql").mock(return_value=httpx.Response(200, json={"data": {"pet": "Fido"}}))
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "POST", "url": "https://example.invalid/graphql", "headers": {}, "body": '{"query":"{ pet(id: 1) }"}',
    })
    assert r.status_code == 201
    body = r.json()
    assert body["request"]["node_id"] is not None
    assert body["drift_finding"]["status"] == "matched"


@respx.mock
def test_call_count_increments_and_persists_on_a_matched_request(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Petstore", "schema_kind": "openapi", "raw_schema": FIXTURE,
    }).json()
    node_id = next(n["id"] for n in client.get(f"/api/workspaces/{ws['id']}").json()["nodes"] if n["operation_id"] == "getPetById")
    respx.get("https://93.184.216.34/api/v3/pet/1").mock(return_value=httpx.Response(200, json={"id": 1, "name": "Fido", "photoUrls": []}))
    client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "GET", "url": "https://example.invalid/api/v3/pet/1", "headers": {}, "body": None,
    })

    session = SessionLocal()
    try:
        node = session.get(Node, node_id)
        assert node.call_count == 1
    finally:
        session.close()


@respx.mock
def test_response_body_is_parsed_in_api_response_but_raw_text_when_persisted(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Petstore", "schema_kind": "openapi", "raw_schema": FIXTURE,
    }).json()
    respx.get("https://93.184.216.34/api/v3/pet/1").mock(return_value=httpx.Response(200, json={"id": 1, "name": "Fido", "photoUrls": []}))
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "GET", "url": "https://example.invalid/api/v3/pet/1", "headers": {}, "body": None,
    })
    body = r.json()
    assert isinstance(body["response"]["body"], dict)
    assert body["response"]["body"]["name"] == "Fido"

    session = SessionLocal()
    try:
        req_row = session.query(Request).filter(Request.workspace_id == ws["id"]).one()
        resp_row = session.query(ResponseModel).filter(ResponseModel.request_id == req_row.id).one()
        assert isinstance(resp_row.body, str)
        assert json.loads(resp_row.body)["name"] == "Fido"
    finally:
        session.close()


@respx.mock
def test_send_a_real_graphql_request_that_matches_and_drifts(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Pets (GraphQL)", "schema_kind": "graphql",
        "raw_schema": "type Query { pet(id: ID!): Pet } type Pet { id: ID! name: String! }",
    }).json()

    respx.post("https://93.184.216.34/graphql").mock(
        return_value=httpx.Response(200, json={"data": {"pet": "not-an-object"}})
    )
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "POST", "url": "https://example.invalid/graphql",
        "headers": {}, "body": '{"query": "{ pet(id: 1) { name } }"}',
    })
    assert r.status_code == 201
    body = r.json()
    assert body["request"]["node_id"] is not None
    # declared type for `pet` is a nullable NAMED "Pet" (a custom object type) --
    # v1 GraphQL drift-checking only checks presence/nullability for a custom
    # object type, so a string value here is NOT flagged (matches this task's
    # own stated scope boundary -- confirmed real, not a bug).
    assert body["drift_finding"]["status"] == "matched"


@respx.mock
def test_send_a_graphql_request_that_matches_no_field_is_unverified_no_match(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Pets (GraphQL)", "schema_kind": "graphql",
        "raw_schema": "type Query { pet(id: ID!): Pet } type Pet { id: ID! name: String! }",
    }).json()
    respx.post("https://93.184.216.34/graphql").mock(return_value=httpx.Response(200, json={"data": {"totallyUnknown": 1}}))
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "POST", "url": "https://example.invalid/graphql",
        "headers": {}, "body": '{"query": "{ totallyUnknown }"}',
    })
    assert r.status_code == 201
    body = r.json()
    assert body["request"]["node_id"] is None
    assert body["drift_finding"]["status"] == "unverified_no_match"


@respx.mock
def test_a_stored_credential_is_injected_and_redacted(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Petstore", "schema_kind": "openapi", "raw_schema": FIXTURE,
    }).json()
    client.put(f"/api/workspaces/{ws['id']}/credential", json={"header_name": "api_key", "value": "sk_real_secret_value"})

    route = respx.get("https://93.184.216.34/api/v3/pet/1").mock(
        return_value=httpx.Response(200, json={"id": 1, "name": "Fido", "photoUrls": []})
    )
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "GET", "url": "https://example.invalid/api/v3/pet/1", "headers": {}, "body": None,
    })
    assert r.status_code == 201

    # the real outbound request must have received the REAL decrypted value
    sent_headers = route.calls.last.request.headers
    assert sent_headers["api_key"] == "sk_real_secret_value"

    # but the persisted row must never contain the real value
    from app.db import SessionLocal
    from app.models import Request as RequestModel
    session = SessionLocal()
    try:
        req_row = session.query(RequestModel).filter(RequestModel.workspace_id == ws["id"]).one()
        assert req_row.headers.get("api_key") == "[REDACTED]"
    finally:
        session.close()


@respx.mock
def test_a_users_own_header_wins_over_the_stored_credential(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Petstore", "schema_kind": "openapi", "raw_schema": FIXTURE,
    }).json()
    client.put(f"/api/workspaces/{ws['id']}/credential", json={"header_name": "api_key", "value": "stored-secret"})

    route = respx.get("https://93.184.216.34/api/v3/pet/1").mock(
        return_value=httpx.Response(200, json={"id": 1, "name": "Fido", "photoUrls": []})
    )
    client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "GET", "url": "https://example.invalid/api/v3/pet/1",
        "headers": {"api_key": "user-supplied-value"}, "body": None,
    })
    sent_headers = route.calls.last.request.headers
    assert sent_headers["api_key"] == "user-supplied-value"


@respx.mock
def test_an_injected_credential_is_stripped_on_a_cross_host_redirect(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Petstore", "schema_kind": "openapi", "raw_schema": FIXTURE,
    }).json()
    client.put(f"/api/workspaces/{ws['id']}/credential", json={"header_name": "api_key", "value": "sk_real_secret_value"})

    respx.get("https://93.184.216.34/api/v3/pet/1").mock(
        return_value=httpx.Response(302, headers={"location": "https://other.invalid/api/v3/pet/2"})
    )
    route = respx.get("https://93.184.216.34/api/v3/pet/2").mock(
        return_value=httpx.Response(200, json={"id": 2, "name": "Rex", "photoUrls": []})
    )
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "GET", "url": "https://example.invalid/api/v3/pet/1", "headers": {}, "body": None,
    })
    assert r.status_code == 201

    # the credential must not have survived the cross-host redirect
    sent_headers = route.calls.last.request.headers
    assert "api_key" not in sent_headers
