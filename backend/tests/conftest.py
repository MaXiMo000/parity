"""Real disposable-Postgres discipline (this author's other project
`loom` already established this pattern for the same reason): tests run
against a real local Postgres, not sqlite or a mock."""

from __future__ import annotations

import base64
import json
import os

import httpx
import itsdangerous
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import DEFAULT_USER_ID, SessionLocal, engine, ensure_default_user
from app.models import Base

TEST_SESSION_SECRET = "test-only-session-secret"
os.environ.setdefault("SESSION_SECRET_KEY", TEST_SESSION_SECRET)
os.environ.setdefault("GITHUB_CLIENT_ID", "test-client-id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("GITHUB_CALLBACK_URL", "http://testserver/api/auth/github/callback")
os.environ.setdefault("FERNET_KEY", "L3RY_MnUUvW0V0jjkBaLpN7RB1P_yBc-K4jSAG6ZmA0=")


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        ensure_default_user(session)
    finally:
        session.close()
    yield
    with engine.begin() as conn:
        conn.execute(text('TRUNCATE workspace, node, "user" RESTART IDENTITY CASCADE'))
    # Deviation from the brief: calling this *inside* the `with engine.begin()`
    # block deadlocks against real Postgres -- the TRUNCATE above takes an
    # ACCESS EXCLUSIVE lock that isn't released until that `with` block
    # commits, but it can't commit until this call returns, and this call's
    # own SELECT on "user" blocks waiting for that same lock. Moving it after
    # the `with` block (so the TRUNCATE has already committed) keeps the
    # fire-and-forget, unclosed-session style the brief asked for while
    # actually running instead of hanging forever.
    ensure_default_user(SessionLocal())


def login_as(client: TestClient, user_id: str) -> None:
    """Signs a real session cookie matching the app's own
    SESSION_SECRET_KEY -- verified directly against the real
    SessionMiddleware/itsdangerous behavior before this plan was
    written. Lets a test authenticate a TestClient without a real GitHub
    OAuth round-trip; every route that needs a real GitHub interaction
    (the login/callback routes themselves) is tested separately, with
    respx mocking the real GitHub calls."""
    signer = itsdangerous.TimestampSigner(os.environ["SESSION_SECRET_KEY"])
    payload = base64.b64encode(json.dumps({"user_id": user_id}).encode("utf-8"))
    signed = signer.sign(payload).decode("utf-8")
    # Deviation from the brief: `client.cookies.set("session", signed)`
    # stamps the cookie with domain="" (unspecified-but-literal-empty).
    # A later real Set-Cookie response (e.g. /logout's deletion cookie)
    # gets its domain resolved from the request host instead, so it never
    # matches/overwrites the manually-set one -- logout would appear to
    # work but the stale cookie keeps getting replayed forever. Routing
    # the cookie through httpx's own extract_cookies (the same code path
    # a real Set-Cookie response goes through) gives it the same
    # domain-matching a real login round trip would, so a later real
    # deletion cookie actually replaces it.
    fake_response = httpx.Response(
        200,
        headers={"set-cookie": f"session={signed}; path=/"},
        request=httpx.Request("GET", str(client.base_url)),
    )
    client.cookies.extract_cookies(fake_response)
