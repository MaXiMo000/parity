import json
import socket
from pathlib import Path

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "petstore-openapi.json").read_text())


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
