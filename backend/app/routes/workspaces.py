"""GET /api/workspaces and GET /api/workspaces/{id} — Phase 0 serves only
the one fixture workspace (app/fixtures.py). Real workspace CRUD against
Postgres is Phase 1 (SPEC.md §10); this route's response shape is already
the real Phase-1 shape."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.fixtures import FIXTURE_WORKSPACE_ID, fixture_edges, fixture_workspace

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.get("")
def list_workspaces() -> list[dict]:
    ws = fixture_workspace()
    return [{"id": ws["id"], "name": ws["name"], "schema_kind": ws["schema_kind"]}]


@router.get("/{workspace_id}")
def get_workspace(workspace_id: str) -> dict:
    if workspace_id != FIXTURE_WORKSPACE_ID:
        raise HTTPException(status_code=404, detail="unknown workspace id (Phase 0 only serves the fixture)")
    ws = fixture_workspace()
    ws["edges"] = [{"from_node": a, "to_node": b} for a, b in fixture_edges()]
    return ws
