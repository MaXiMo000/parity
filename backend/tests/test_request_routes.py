from fastapi.testclient import TestClient

from app.fixtures import FIXTURE_WORKSPACE_ID
from app.main import app

client = TestClient(app)


def test_send_matched_node():
    r = client.post(f"/api/workspaces/{FIXTURE_WORKSPACE_ID}/requests", json={"node_id": "get_task"})
    assert r.status_code == 200
    body = r.json()
    assert body["drift_finding"]["status"] == "matched"
    assert body["response"]["status_code"] == 200
    assert body["response"]["body"]["id"] == "t1"


def test_send_violated_node():
    # create_task's canned response is deliberately missing the required
    # "done" field its own declared_response_schema requires.
    r = client.post(f"/api/workspaces/{FIXTURE_WORKSPACE_ID}/requests", json={"node_id": "create_task"})
    assert r.status_code == 200
    body = r.json()
    assert body["drift_finding"]["status"] == "violated"
    assert "done" in body["drift_finding"]["detail"]
    assert "done" not in body["response"]["body"]


def test_send_unknown_node_is_404():
    r = client.post(f"/api/workspaces/{FIXTURE_WORKSPACE_ID}/requests", json={"node_id": "not-a-real-node"})
    assert r.status_code == 404


def test_send_unknown_workspace_is_404():
    r = client.post("/api/workspaces/not-real/requests", json={"node_id": "get_task"})
    assert r.status_code == 404
