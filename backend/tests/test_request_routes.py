from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_send_against_a_real_workspace_is_honestly_not_implemented():
    ws = client.post("/api/workspaces", json={
        "name": "x", "schema_kind": "openapi",
        "raw_schema": {"openapi": "3.0.0", "info": {"title": "t", "version": "1"}, "paths": {}},
    }).json()
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={"node_id": "whatever"})
    assert r.status_code == 501
    assert "Phase 2" in r.json()["detail"]


def test_send_against_unknown_workspace_is_404():
    r = client.post("/api/workspaces/00000000-0000-0000-0000-000000000099/requests", json={"node_id": "x"})
    assert r.status_code == 404
