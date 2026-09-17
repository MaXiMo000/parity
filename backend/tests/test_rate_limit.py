"""The real adversarial proof the rate limiter actually holds (2026-09-18
security-hardening plan) -- conftest.py disables the limiter globally so
the rest of this suite's shared TestClient doesn't trip it; this file
re-enables it deliberately and resets its storage before/after so it
never leaks state into any other test file."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import User
from app.ratelimit import limiter
from tests.conftest import login_as

client = TestClient(app)
FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "petstore-openapi.json").read_text())


@pytest.fixture(autouse=True)
def _real_rate_limiting():
    limiter.enabled = True
    limiter.reset()
    yield
    limiter.reset()
    limiter.enabled = False


@pytest.fixture(autouse=True)
def _authenticated():
    session = SessionLocal()
    try:
        user = User(github_id="rate-limit-test-github-id", username="ratelimituser")
        session.add(user)
        session.commit()
        user_id = user.id
    finally:
        session.close()
    login_as(client, user_id)


def test_create_workspace_is_rejected_after_its_real_limit():
    # The real decorated limit is 10/minute -- fire 11 real requests and
    # confirm the 11th is the one that gets rejected, not an earlier or
    # later one (proves the boundary is exact, not approximate).
    responses = [
        client.post("/api/workspaces", json={"name": f"ws-{i}", "schema_kind": "openapi", "raw_schema": FIXTURE})
        for i in range(11)
    ]
    statuses = [r.status_code for r in responses]
    assert statuses[:10] == [201] * 10
    assert statuses[10] == 429
