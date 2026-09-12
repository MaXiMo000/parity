import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app
from app.models import User
from app.db import SessionLocal
from tests.conftest import login_as

client = TestClient(app)


def test_login_redirects_to_a_real_shaped_github_authorize_url():
    r = client.get("/api/auth/github/login", follow_redirects=False)
    assert r.status_code in (302, 307)
    location = r.headers["location"]
    assert location.startswith("https://github.com/login/oauth/authorize")
    assert "client_id=test-client-id" in location
    assert "state=" in location


def test_callback_rejects_a_state_mismatch():
    # Never having called /login means no oauth_state is in the session --
    # a callback claiming any state at all must be rejected.
    r = client.get("/api/auth/github/callback?code=abc&state=whatever-not-real")
    assert r.status_code == 400


@respx.mock
def test_callback_completes_a_real_flow_and_creates_a_real_user():
    # Establish the real oauth_state the way a real browser would: call
    # /login first, extract the state from the real redirect Location.
    login_resp = client.get("/api/auth/github/login", follow_redirects=False)
    location = login_resp.headers["location"]
    state = location.split("state=")[1].split("&")[0]

    respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "gho_fake", "token_type": "bearer"})
    )
    respx.get("https://api.github.com/user").mock(
        return_value=httpx.Response(200, json={"id": 583231, "login": "octocat"})
    )

    r = client.get(f"/api/auth/github/callback?code=realcode&state={state}", follow_redirects=False)
    assert r.status_code in (302, 307)

    session = SessionLocal()
    try:
        user = session.query(User).filter(User.github_id == "583231").one()
        assert user.username == "octocat"
    finally:
        session.close()

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "octocat"


def test_me_without_a_session_is_401():
    fresh_client = TestClient(app)
    r = fresh_client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_with_a_signed_test_session_works():
    fresh_client = TestClient(app)
    session = SessionLocal()
    try:
        user = User(github_id="999", username="testuser")
        session.add(user)
        session.commit()
        user_id = user.id
    finally:
        session.close()
    login_as(fresh_client, user_id)
    r = fresh_client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == "testuser"


def test_logout_clears_the_session():
    fresh_client = TestClient(app)
    session = SessionLocal()
    try:
        user = User(github_id="888", username="logout-test")
        session.add(user)
        session.commit()
        user_id = user.id
    finally:
        session.close()
    login_as(fresh_client, user_id)
    assert fresh_client.get("/api/auth/me").status_code == 200
    fresh_client.post("/api/auth/logout")
    assert fresh_client.get("/api/auth/me").status_code == 401
