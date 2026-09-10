"""POST /api/workspaces/{id}/requests — Phase 0: a canned, deterministic
fake result per fixture node, never a real proxy call. Real request
execution against the real target server, real curl parsing, and real
schema validation are Phase 2 (SPEC.md §10, §7.3's SSRF-guarded proxy).
This route's response shape is already the real Phase-2 shape, so the
frontend built against it today doesn't change later.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.fixtures import FIXTURE_WORKSPACE_ID, fixture_workspace

router = APIRouter(prefix="/api/workspaces", tags=["requests"])

# One canned (request, response, drift_finding) per fixture node id.
# create_task's response is deliberately missing "done" -- the one
# violated node the fixture is built to demonstrate (matches SPEC.md's
# own "mostly clean, one real finding" fixture discipline, see loom's
# own fixture for the precedent).
_CANNED: dict[str, dict[str, Any]] = {
    "list_tasks": {
        "response": {"status_code": 200, "body": [{"id": "t1", "title": "Write SPEC", "done": True}]},
        "drift_finding": {"status": "matched", "detail": "response matches the declared array-of-task schema"},
    },
    "create_task": {
        "response": {"status_code": 201, "body": {"id": "t2", "title": "Ship Phase 0"}},
        "drift_finding": {
            "status": "violated",
            "detail": "response is missing required field 'done' declared in the response schema",
        },
    },
    "get_task": {
        "response": {"status_code": 200, "body": {"id": "t1", "title": "Write SPEC", "done": True}},
        "drift_finding": {"status": "matched", "detail": "response matches the declared task schema"},
    },
    "update_task": {
        "response": {"status_code": 200, "body": {"id": "t1", "title": "Write SPEC", "done": False}},
        "drift_finding": {"status": "matched", "detail": "response matches the declared task schema"},
    },
    "delete_task": {
        "response": {"status_code": 204, "body": None},
        "drift_finding": {"status": "matched", "detail": "204 with no body, as declared"},
    },
}


@router.post("/{workspace_id}/requests")
def send_request(workspace_id: str, body: dict) -> dict:
    if workspace_id != FIXTURE_WORKSPACE_ID:
        raise HTTPException(status_code=404, detail="unknown workspace id")
    node_id = body.get("node_id")
    canned = _CANNED.get(node_id)
    if canned is None:
        raise HTTPException(status_code=404, detail="unknown node id")

    node = next(n for n in fixture_workspace()["nodes"] if n["id"] == node_id)
    return {
        "request": {"node_id": node_id, "method": node["method"], "url": f"https://example.invalid{node['path_template']}"},
        "response": canned["response"],
        "drift_finding": canned["drift_finding"],
    }
