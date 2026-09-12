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
    request.session["oauth_state"] = state
    redirect_uri = os.environ["GITHUB_CALLBACK_URL"]
    return RedirectResponse(build_authorize_url(redirect_uri, state))


@router.get("/github/callback")
def github_callback(request: Request, code: str, state: str, session: Session = Depends(get_session)):
    expected_state = request.session.pop("oauth_state", None)
    if not expected_state or expected_state != state:
        raise HTTPException(status_code=400, detail="invalid OAuth state")

    redirect_uri = os.environ["GITHUB_CALLBACK_URL"]
    try:
        token = exchange_code_for_token(code, redirect_uri)
        profile = fetch_github_user(token)
    except GitHubOAuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    github_id = str(profile.get("id"))
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
