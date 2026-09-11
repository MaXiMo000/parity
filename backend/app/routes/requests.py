"""POST /api/workspaces/{id}/requests — Phase 0 returned a canned fake
result per fixture node; Phase 1 has real workspaces but no real request
proxying yet (that's Phase 2's SSRF-guarded proxy, SPEC.md §7.3). Rather
than removing this route (the frontend's Send button already calls it,
and the route SHAPE is real v1 API surface per SPEC.md §7.6), it now
answers honestly: 501, not a guess."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Workspace

router = APIRouter(prefix="/api/workspaces", tags=["requests"])


@router.post("/{workspace_id}/requests")
def send_request(workspace_id: str, body: dict, session: Session = Depends(get_session)) -> dict:
    if session.get(Workspace, workspace_id) is None:
        raise HTTPException(status_code=404, detail="unknown workspace id")
    raise HTTPException(status_code=501, detail="real request execution arrives in Phase 2 (SPEC.md §7.3/§10)")
