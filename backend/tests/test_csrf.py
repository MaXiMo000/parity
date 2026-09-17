"""The real adversarial proof CSRF protection actually holds (2026-09-18
security-hardening plan): a mutating route must reject a request with no
token, a wrong token, or a token that belongs to a different session --
and must accept the real one. login_as (conftest.py) sets a correct
X-CSRF-Token as a default header on its client, which is why every other
test file in this suite doesn't need to think about this at all; this
file is the one place that deliberately breaks that default."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.models import User
from app.main import app
from tests.conftest import login_as

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "petstore-openapi.json").read_text())


def _new_user(username: str) -> str:
    session = SessionLocal()
    try:
        user = User(github_id=f"csrf-test-{username}", username=username)
        session.add(user)
        session.commit()
        return user.id
    finally:
        session.close()


def test_create_workspace_with_no_csrf_header_is_rejected():
    client = TestClient(app)
    login_as(client, _new_user("no-header"))
    del client.headers["x-csrf-token"]  # undo login_as's own default for this one test
    r = client.post("/api/workspaces", json={"name": "x", "schema_kind": "openapi", "raw_schema": FIXTURE})
    assert r.status_code == 403


def test_create_workspace_with_the_wrong_csrf_token_is_rejected():
    client = TestClient(app)
    login_as(client, _new_user("wrong-token"))
    client.headers["X-CSRF-Token"] = "a-token-that-does-not-match-the-session"
    r = client.post("/api/workspaces", json={"name": "x", "schema_kind": "openapi", "raw_schema": FIXTURE})
    assert r.status_code == 403


def test_create_workspace_with_another_sessions_real_token_is_still_rejected():
    # A real token that really exists -- just not for THIS session. Proves
    # the check is a real per-session comparison, not "is this any known
    # token at all."
    victim = TestClient(app)
    login_as(victim, _new_user("victim"))

    attacker = TestClient(app)
    real_token_from_a_different_session = login_as(attacker, _new_user("attacker"))

    victim.headers["X-CSRF-Token"] = real_token_from_a_different_session
    r = victim.post("/api/workspaces", json={"name": "x", "schema_kind": "openapi", "raw_schema": FIXTURE})
    assert r.status_code == 403


def test_create_workspace_with_the_real_matching_token_succeeds():
    client = TestClient(app)
    login_as(client, _new_user("real-token"))
    r = client.post("/api/workspaces", json={"name": "x", "schema_kind": "openapi", "raw_schema": FIXTURE})
    assert r.status_code == 201


def test_get_me_returns_a_real_csrf_token_for_the_frontend_to_use():
    client = TestClient(app)
    token = login_as(client, _new_user("token-exposure"))
    me = client.get("/api/auth/me").json()
    assert me["csrf_token"] == token


@pytest.mark.parametrize("method,path,kwargs", [
    ("put", "/api/workspaces/{ws_id}/credential", {"json": {"header_name": "x", "value": "y"}}),
    ("delete", "/api/workspaces/{ws_id}/credential", {}),
])
def test_credential_routes_require_csrf_too(method, path, kwargs):
    client = TestClient(app)
    login_as(client, _new_user(f"cred-{method}"))
    ws = client.post("/api/workspaces", json={"name": "x", "schema_kind": "openapi", "raw_schema": FIXTURE}).json()

    del client.headers["x-csrf-token"]
    r = getattr(client, method)(path.format(ws_id=ws["id"]), **kwargs)
    assert r.status_code == 403
