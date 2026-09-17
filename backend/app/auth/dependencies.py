"""Real per-user access control (SPEC.md Phase 3: "workspaces scoped per
user"). get_current_user reads the real session GitHub OAuth sets;
get_owned_workspace is the one place every workspace-scoped route checks
that the workspace it's about to touch really belongs to the real
logged-in user -- a 404 (not 403) on a mismatch, so a request against
someone else's workspace id can't even confirm that id exists.
require_csrf (2026-09-18 security-hardening plan) is the anti-CSRF
boundary every mutating route depends on."""

from __future__ import annotations

import secrets
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


def require_csrf(request: Request) -> None:
    """The double-submit-token CSRF defense every mutating route depends
    on (2026-09-18 security-hardening plan). Needed because the session
    cookie is SameSite=None in production (required for the split-origin
    deploy, SPEC.md's own deploy-readiness goal) -- SameSite=None removes
    the CSRF protection SameSite=Lax/Strict would otherwise give for free,
    and CORS alone doesn't cover this: CORS blocks a cross-site page's JS
    from *reading* a response, not from a hidden form *firing* the
    request with the ambient session cookie. A cross-site form can't set
    a custom header, so requiring one here (matched against a value only
    a real prior login could have produced) closes that gap. Constant-time
    comparison (secrets.compare_digest) so a timing side-channel can't
    help an attacker guess the real token byte-by-byte."""
    session_token = request.session.get("csrf_token")
    header_token = request.headers.get("x-csrf-token")
    if not session_token or not header_token or not secrets.compare_digest(header_token, session_token):
        raise HTTPException(status_code=403, detail="missing or invalid CSRF token")


def get_owned_workspace(workspace_id: str, current_user: User, session: Session) -> Workspace:
    try:
        uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown workspace id")
    workspace = session.get(Workspace, workspace_id)
    if workspace is None or workspace.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="unknown workspace id")
    return workspace
