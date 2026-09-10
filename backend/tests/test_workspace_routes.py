from fastapi.testclient import TestClient

from app.fixtures import FIXTURE_WORKSPACE_ID
from app.main import app

client = TestClient(app)


def test_list_workspaces_returns_the_fixture():
    r = client.get("/api/workspaces")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["id"] == FIXTURE_WORKSPACE_ID
    assert body[0]["schema_kind"] == "openapi"


def test_get_workspace_includes_nodes_and_edges():
    r = client.get(f"/api/workspaces/{FIXTURE_WORKSPACE_ID}")
    assert r.status_code == 200
    body = r.json()
    assert len(body["nodes"]) == 5
    assert len(body["edges"]) == 3
    node_ids = {n["id"] for n in body["nodes"]}
    for e in body["edges"]:
        assert e["from_node"] in node_ids
        assert e["to_node"] in node_ids


def test_get_unknown_workspace_is_404():
    r = client.get("/api/workspaces/not-a-real-id")
    assert r.status_code == 404
