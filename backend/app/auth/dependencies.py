"""Real per-user access control (SPEC.md Phase 3: "workspaces scoped per
user"). get_current_user reads the real session GitHub OAuth sets;
get_owned_workspace is the one place every workspace-scoped route checks
that the workspace it's about to touch really belongs to the real
logged-in user -- a 404 (not 403) on a mismatch, so a request against
someone else's workspace id can't even confirm that id exists."""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User, Workspace


def get_current_user(request: Request, session: Session = Depends(get_session)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="not authenticated")
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


def get_owned_workspace(workspace_id: str, current_user: User, session: Session) -> Workspace:
    try:
        uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown workspace id")
    workspace = session.get(Workspace, workspace_id)
    if workspace is None or workspace.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="unknown workspace id")
    return workspace
