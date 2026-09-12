"""Real GitHub OAuth routes (SPEC.md §7.6): the standard
authorization-code flow, a signed-cookie session (Starlette's
SessionMiddleware, registered in app/main.py), and a real upsert of the
authenticated GitHub user."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.github import GitHubOAuthError, build_authorize_url, exchange_code_for_token, fetch_github_user, new_state
from app.db import get_session
from app.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/github/login")
def github_login(request: Request):
    state = new_state()
    # A list, not a single scalar -- opening "Sign in with GitHub" in two
    # tabs before completing either used to make the FIRST tab's callback
    # fail, since the second /login call overwrote the only stored state
    # in the shared session cookie (Phase 3a's final review, finding I5,
    # reproduced live). Capped so a user who abandons many login attempts
    # doesn't grow the session cookie unboundedly.
    states = request.session.setdefault("oauth_states", [])
    states.append(state)
    del states[:-5]
    request.session["oauth_states"] = states
    redirect_uri = os.environ["GITHUB_CALLBACK_URL"]
    return RedirectResponse(build_authorize_url(redirect_uri, state))


@router.get("/github/callback")
def github_callback(request: Request, code: str, state: str, session: Session = Depends(get_session)):
    states = request.session.get("oauth_states", [])
    if state not in states:
        raise HTTPException(status_code=400, detail="invalid OAuth state")
    states.remove(state)
    request.session["oauth_states"] = states

    redirect_uri = os.environ["GITHUB_CALLBACK_URL"]
    try:
        token = exchange_code_for_token(code, redirect_uri)
        profile = fetch_github_user(token)
    except GitHubOAuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not profile.get("id"):
        raise HTTPException(status_code=502, detail="GitHub profile response is missing an id")
    github_id = str(profile["id"])
    username = profile.get("login") or github_id
    user = session.query(User).filter(User.github_id == github_id).one_or_none()
    if user is None:
        user = User(github_id=github_id, username=username)
        session.add(user)
    else:
        user.username = username
    session.commit()

    request.session["user_id"] = user.id
    frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
    return RedirectResponse(frontend_origin)


@router.get("/me")
def auth_me(current_user: User = Depends(get_current_user)) -> dict:
    return {"id": current_user.id, "username": current_user.username}


@router.post("/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"status": "ok"}
