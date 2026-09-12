import json
import socket
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import User
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


@respx.mock
def test_create_workspace_from_a_real_url(monkeypatch):
    # "example.invalid" is RFC 2606 reserved and never actually resolves --
    # respx mocks the HTTP layer but not DNS, so fake a public-IP resolution
    # for our own pre-fetch safety check (app/schema/openapi.py's send_pinned).
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.get("https://93.184.216.34/openapi.json").mock(return_value=httpx.Response(200, json=FIXTURE))
    r = client.post("/api/workspaces", json={
        "name": "Petstore", "schema_kind": "openapi",
        "schema_source_url": "https://example.invalid/openapi.json",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Petstore"
    assert body["node_count"] > 10


def test_create_workspace_from_a_pasted_raw_schema():
    r = client.post("/api/workspaces", json={
        "name": "Petstore (pasted)", "schema_kind": "openapi", "raw_schema": FIXTURE,
    })
    assert r.status_code == 201
    assert r.json()["node_count"] > 10


def test_create_workspace_requires_exactly_one_source():
    r = client.post("/api/workspaces", json={"name": "x", "schema_kind": "openapi"})
    assert r.status_code == 422
    r2 = client.post("/api/workspaces", json={
        "name": "x", "schema_kind": "openapi",
        "schema_source_url": "https://example.invalid/x.json", "raw_schema": FIXTURE,
    })
    assert r2.status_code == 422


def test_create_workspace_rejects_an_invalid_spec():
    r = client.post("/api/workspaces", json={
        "name": "bad", "schema_kind": "openapi", "raw_schema": {"not": "openapi"},
    })
    assert r.status_code == 422


@respx.mock
def test_create_workspace_url_fetch_failure_is_502():
    respx.get("https://93.184.216.34/down.json").mock(side_effect=httpx.ConnectError("boom"))
    r = client.post("/api/workspaces", json={
        "name": "x", "schema_kind": "openapi", "schema_source_url": "https://example.invalid/down.json",
    })
    assert r.status_code == 502


def test_list_and_get_real_workspace():
    created = client.post("/api/workspaces", json={
        "name": "Petstore", "schema_kind": "openapi", "raw_schema": FIXTURE,
    }).json()

    listed = client.get("/api/workspaces").json()
    assert any(w["id"] == created["id"] for w in listed)

    got = client.get(f"/api/workspaces/{created['id']}").json()
    assert got["name"] == "Petstore"
    assert got["base_path"] == "/api/v3"  # the real Petstore fixture's servers[0].url
    assert got["schema_source"] == "pasted"  # this test creates the workspace via raw_schema, not a URL
    assert len(got["nodes"]) == created["node_count"]
    assert len(got["edges"]) > 0
    node_ids = {n["id"] for n in got["nodes"]}
    for e in got["edges"]:
        assert e["from_node"] in node_ids
        assert e["to_node"] in node_ids
    # real field names, matching SPEC.md §7.5
    sample = got["nodes"][0]
    for key in ("id", "kind", "method", "path_template", "operation_id",
                "declared_request_schema", "declared_response_schema", "call_count"):
        assert key in sample


def test_get_unknown_workspace_is_404():
    r = client.get("/api/workspaces/00000000-0000-0000-0000-000000000099")
    assert r.status_code == 404


def test_get_a_malformed_workspace_id_is_404_not_a_crash():
    r = client.get("/api/workspaces/not-a-real-uuid")
    assert r.status_code == 404


GRAPHQL_SDL = """
type Query {
  pet(id: ID!): Pet
}

type Pet {
  id: ID!
  name: String!
}
"""

GRAPHQL_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "countries-graphql-introspection.json").read_text()
)


def test_create_workspace_from_a_pasted_graphql_sdl():
    r = client.post("/api/workspaces", json={
        "name": "Pets (GraphQL)", "schema_kind": "graphql", "raw_schema": GRAPHQL_SDL,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["schema_kind"] == "graphql"
    assert body["node_count"] == 1


@respx.mock
def test_create_workspace_from_a_real_graphql_url(monkeypatch):
    # Reuses the same real, live-fetched introspection fixture Task 1's
    # test_graphql_schema.py verifies parse_graphql against directly --
    # a hand-rolled minimal introspection payload risks being rejected by
    # build_client_schema for a reason never actually checked against the
    # real library (e.g. a missing built-in scalar type entry).
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.post("https://93.184.216.34/graphql").mock(
        return_value=httpx.Response(200, json=GRAPHQL_FIXTURE)
    )
    r = client.post("/api/workspaces", json={
        "name": "Countries (GraphQL)", "schema_kind": "graphql",
        "schema_source_url": "https://example.invalid/graphql",
    })
    assert r.status_code == 201
    assert r.json()["node_count"] == 6


def test_create_workspace_rejects_a_non_string_graphql_raw_schema():
    r = client.post("/api/workspaces", json={
        "name": "bad", "schema_kind": "graphql", "raw_schema": {"not": "a string"},
    })
    assert r.status_code == 422


def test_create_workspace_rejects_invalid_schema_kind():
    r = client.post("/api/workspaces", json={
        "name": "x", "schema_kind": "soap", "raw_schema": "irrelevant",
    })
    assert r.status_code == 422
