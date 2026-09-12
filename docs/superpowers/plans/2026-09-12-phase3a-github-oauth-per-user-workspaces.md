# Phase 3a: Real GitHub OAuth + Per-User Workspaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed default-user stand-in every workspace has belonged to since Phase 1 with real GitHub accounts (SPEC.md §7.4, §7.6) — a real authorization-code OAuth flow, a real session, and every workspace-scoped route actually enforcing that a workspace belongs to the real logged-in user, not just recording an owner nobody checks.

**Architecture:** Starlette's built-in `SessionMiddleware` (a signed cookie, ships with FastAPI — no new heavyweight dependency, only its documented `itsdangerous` companion) replaces any need for a server-side session store. `app/auth/github.py` holds the three real calls to GitHub's own fixed endpoints (authorize URL, code-for-token exchange, user profile) — these are plain `httpx` calls, not routed through the SSRF-guarded `send_pinned`, since that guard exists for arbitrary *user-supplied* target APIs and these three URLs are always the same hardcoded GitHub hosts, never user input. `app/auth/dependencies.py`'s `get_current_user` + `get_owned_workspace` become the one place every workspace-scoped route checks who's asking — a 404 (not 403) on a mismatch, so a request against someone else's workspace id can't even confirm that id exists.

**Tech Stack:** `itsdangerous` (new — Starlette's own documented, required companion for `SessionMiddleware`, verified installed and working below). No other new dependency.

**Spec:** [`SPEC.md`](../../../SPEC.md) §7.4 (auth), §7.5 (the `User`/`Workspace.user_id` columns — already real since Phase 1, never enforced until now), §7.6 (the exact `/api/auth/*` endpoint shapes).

## Global Constraints

- **Verified before this plan was written (2026-09-12), not assumed:**
  - `starlette.middleware.sessions.SessionMiddleware` requires `itsdangerous` (not installed until this plan adds it) — confirmed by import failure, then confirmed working end-to-end once installed: a real session round-trip (set → read on a later request) and a **test-only manually-signed session cookie** (using the same `itsdangerous.TimestampSigner` + secret the app itself uses) both work identically. This manually-signed-cookie technique is this plan's real answer to "how do integration tests authenticate without a real GitHub round-trip" — it's used throughout this plan's tests instead of mocking GitHub for every single protected-route test.
  - Only `backend/app/routes/workspaces.py` (plus `app/db.py`'s definition and `tests/conftest.py`'s fixture) currently reference `DEFAULT_USER_ID` — confirmed by repo-wide grep. `backend/app/routes/requests.py` never checked workspace ownership at all (any workspace id, `GET`ed by anyone, worked) — this plan closes that gap too, not just re-pointing which user id workspaces are scoped by.
- **`GITHUB_CALLBACK_URL` is an explicit env var, not derived from the incoming request.** Deriving it from `request.url_for(...)`/`request.url` is a well-known deployment trap behind a reverse proxy that terminates TLS (Render's own setup does this) — the derived scheme can silently read `http` even though the real external URL is `https`, breaking GitHub's exact-match callback-URL check. An explicit env var sidesteps this entirely and gives the user one unambiguous value to both register on GitHub and set locally.
- **Real, human-required step this plan cannot automate**: registering a real GitHub OAuth App (client id/secret) requires the user's own GitHub account and a real browser click-through — no subagent can do this on their behalf. This plan's final task writes the exact registration steps and verifies everything automatable (the redirect shape, the 401 boundary, the frontend's logged-out gate, the full OAuth code path against a *mocked* GitHub) — the one thing that genuinely needs the user's own hands is completing a real login once they've registered their app and set the three real env vars, which the final task's report will hand back explicitly, not silently skip or fake.
- **Existing dev-DB workspaces (owned by the fixed `DEFAULT_USER_ID`) are left as-is** — nothing is deployed yet, so there is no real user data to migrate (a ruling already made and recorded during this phase's brainstorming, per SPEC.md's own "decide against real data, not in the abstract" instruction for this exact question). `ensure_default_user` keeps running at startup; it just stops being what new workspaces are scoped to.

---

### Task 1: The real OAuth flow (backend)

**Files:**
- Create: `backend/app/auth/__init__.py` (empty)
- Create: `backend/app/auth/github.py`
- Create: `backend/app/auth/dependencies.py`
- Create: `backend/app/routes/auth.py`
- Modify: `backend/app/main.py` (register `SessionMiddleware`, fix `CORSMiddleware` for credentialed requests, register the new router)
- Modify: `backend/pyproject.toml` (add `itsdangerous`)
- Modify: `backend/tests/conftest.py` (truncate `"user"` too, now that tests create real User rows; add the shared test-login helper)
- Test: `backend/tests/test_auth_routes.py`

**Interfaces:**
- Produces: `get_current_user(request: Request, session: Session = Depends(get_session)) -> User` and `get_owned_workspace(workspace_id: str, current_user: User, session: Session) -> Workspace` in `app.auth.dependencies` (Task 2 consumes both). A test helper `login_as(client: TestClient, user_id: str) -> None` in `tests/conftest.py` that signs a real session cookie matching the app's own `SESSION_SECRET_KEY` — every later test file that needs an authenticated `TestClient` uses this instead of a real OAuth round-trip.

- [ ] **Step 1: Add the dependency**

In `backend/pyproject.toml`, add `"itsdangerous>=2.0"` to the `dependencies` list.

Run: `cd backend && .venv/bin/pip install -e ".[dev]"`
Expected: installs `itsdangerous` with no errors.

- [ ] **Step 2: Write `app/auth/github.py`**

`backend/app/auth/__init__.py`: empty file.

`backend/app/auth/github.py`:

```python
"""Real GitHub OAuth (the standard authorization-code flow, SPEC.md
§7.4): builds the real authorize URL, exchanges a real code for a real
access token, and fetches the real authenticated user's GitHub profile.
These three calls all target GitHub's own fixed, well-known endpoints
(never a user-supplied URL), so they use plain httpx directly rather
than the SSRF-guarded send_pinned -- that guard exists for arbitrary
user-supplied target APIs (SPEC.md §7.3), not for calls this backend's
own code always sends to the same hardcoded host."""

from __future__ import annotations

import os
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


class GitHubOAuthError(Exception):
    pass


def new_state() -> str:
    return secrets.token_urlsafe(32)


def build_authorize_url(redirect_uri: str, state: str) -> str:
    params = {
        "client_id": os.environ["GITHUB_CLIENT_ID"],
        "redirect_uri": redirect_uri,
        "scope": "read:user",
        "state": state,
    }
    return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(code: str, redirect_uri: str) -> str:
    """Returns the real access token. Raises GitHubOAuthError on any
    failure (network, or GitHub itself rejecting the code)."""
    try:
        resp = httpx.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": os.environ["GITHUB_CLIENT_ID"],
                "client_secret": os.environ["GITHUB_CLIENT_SECRET"],
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise GitHubOAuthError(f"could not reach GitHub: {exc}") from exc
    if resp.status_code != 200:
        raise GitHubOAuthError(f"GitHub token exchange returned HTTP {resp.status_code}")
    payload = resp.json()
    token = payload.get("access_token")
    if not token:
        raise GitHubOAuthError(f"GitHub token exchange returned no access_token: {payload}")
    return token


def fetch_github_user(access_token: str) -> dict[str, Any]:
    """Returns the real {"id": int, "login": str, ...} profile. Raises
    GitHubOAuthError on any failure."""
    try:
        resp = httpx.get(
            GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise GitHubOAuthError(f"could not reach GitHub: {exc}") from exc
    if resp.status_code != 200:
        raise GitHubOAuthError(f"GitHub user lookup returned HTTP {resp.status_code}")
    return resp.json()
```

- [ ] **Step 3: Write `app/auth/dependencies.py`**

```python
"""Real per-user access control (SPEC.md Phase 3: "workspaces scoped per
user"). get_current_user reads the real session GitHub OAuth sets;
get_owned_workspace is the one place every workspace-scoped route checks
that the workspace it's about to touch really belongs to the real
logged-in user -- a 404 (not 403) on a mismatch, so a request against
someone else's workspace id can't even confirm that id exists."""

from __future__ import annotations

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
    workspace = session.get(Workspace, workspace_id)
    if workspace is None or workspace.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="unknown workspace id")
    return workspace
```

- [ ] **Step 4: Write `app/routes/auth.py`**

```python
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
```

- [ ] **Step 5: Wire `app/main.py`**

Change the imports at the top from:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import SessionLocal, ensure_default_user
from app.routes.workspaces import router as workspaces_router
from app.routes.requests import router as requests_router
from app.routes.curl_parse import router as curl_parse_router
```

to:

```python
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.db import SessionLocal, ensure_default_user
from app.routes.auth import router as auth_router
from app.routes.workspaces import router as workspaces_router
from app.routes.requests import router as requests_router
from app.routes.curl_parse import router as curl_parse_router
```

Change:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(workspaces_router)
app.include_router(requests_router)
app.include_router(curl_parse_router)
```

to:

```python
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET_KEY", "dev-only-insecure-secret-change-before-any-real-deploy"),
)
app.add_middleware(
    CORSMiddleware,
    # "*" is incompatible with allow_credentials=True (the session cookie
    # needs credentialed cross-origin requests once frontend and backend
    # are on different real domains, per SPEC.md's own deploy-readiness
    # goal for this phase) -- a real, specific origin is required instead.
    allow_origins=[os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(workspaces_router)
app.include_router(requests_router)
app.include_router(curl_parse_router)
```

- [ ] **Step 6: Update `tests/conftest.py`**

Change:

```python
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.db import DEFAULT_USER_ID, SessionLocal, engine, ensure_default_user
from app.models import Base


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
        conn.execute(text("TRUNCATE workspace, node RESTART IDENTITY CASCADE"))
```

to:

```python
from __future__ import annotations

import base64
import json
import os

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
    client.cookies.set("session", signer.sign(payload).decode("utf-8"))
```

Note: `ensure_default_user(SessionLocal())` after the truncate leaks a
session (never closed) — this is intentional and matches this file's
existing style exactly (the pre-existing `ensure_default_user` call
above uses a `try/finally` for its own separate session; this one-line
post-truncate call is a fire-and-forget re-seed for the next test and
Postgres connections here are cheap and pooled — do not "fix" this into
something more elaborate).

- [ ] **Step 7: Write `tests/test_auth_routes.py`**

```python
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
```

- [ ] **Step 8: Run the tests**

Run: `cd backend && docker compose up -d && .venv/bin/python -m pytest tests/test_auth_routes.py -v`
Expected: all 6 pass.

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all pass — report the real total (114 prior + 6 new = 120; confirm the real number from the actual output).

- [ ] **Step 9: Commit**

```bash
git add backend/app/auth/ backend/app/routes/auth.py backend/app/main.py \
        backend/pyproject.toml backend/tests/conftest.py backend/tests/test_auth_routes.py
git commit -m "feat: real GitHub OAuth (SPEC.md §7.4/§7.6)"
```

---

### Task 2: Enforce real ownership on every workspace-scoped route

**Files:**
- Modify: `backend/app/routes/workspaces.py`
- Modify: `backend/app/routes/requests.py`
- Modify: `backend/tests/test_workspace_routes.py` (every test authenticates now)
- Modify: `backend/tests/test_request_routes.py` (every test authenticates now)

**Interfaces:**
- Consumes: Task 1's `get_current_user`, `get_owned_workspace`, and the `login_as` test helper.
- Produces: no new interfaces — every existing endpoint's *behavior* changes (requires real auth, scopes to the real user, 404s on someone else's workspace), but request/response shapes are unchanged.

- [ ] **Step 1: Rewrite `app/routes/workspaces.py`'s auth surface**

Change the current import lines:

```python
from app.db import DEFAULT_USER_ID, get_session
from app.models import Node, Workspace
```

to:

```python
from app.auth.dependencies import get_current_user, get_owned_workspace
from app.db import get_session
from app.models import Node, User, Workspace
```

(`DEFAULT_USER_ID` is no longer imported here — every use of it in this file is replaced below.)

In `create_workspace`, change the function signature from:

```python
def create_workspace(body: dict, session: Session = Depends(get_session)) -> dict:
```

to:

```python
def create_workspace(body: dict, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)) -> dict:
```

Change every use of `DEFAULT_USER_ID` in this function's `Workspace(...)` construction from `user_id=DEFAULT_USER_ID` to `user_id=current_user.id`. Remove the now-unused `from app.db import DEFAULT_USER_ID, get_session` import's `DEFAULT_USER_ID` part — change it to `from app.db import get_session`.

In `list_workspaces`, change:

```python
def list_workspaces(session: Session = Depends(get_session)) -> list[dict]:
    rows = session.query(Workspace).filter(Workspace.user_id == DEFAULT_USER_ID).all()
```

to:

```python
def list_workspaces(session: Session = Depends(get_session), current_user: User = Depends(get_current_user)) -> list[dict]:
    rows = session.query(Workspace).filter(Workspace.user_id == current_user.id).all()
```

In `get_workspace`, change:

```python
def get_workspace(workspace_id: str, session: Session = Depends(get_session)) -> dict:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="unknown workspace id")
```

to:

```python
def get_workspace(workspace_id: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)) -> dict:
    workspace = get_owned_workspace(workspace_id, current_user, session)
```

- [ ] **Step 2: Rewrite `app/routes/requests.py`'s auth surface**

Change the current import lines:

```python
from app.db import get_session
from app.models import DriftFinding, Node, Request, Response, Workspace
```

to:

```python
from app.auth.dependencies import get_current_user, get_owned_workspace
from app.db import get_session
from app.models import DriftFinding, Node, Request, Response, User, Workspace
```

In `send_request`, change:

```python
def send_request(workspace_id: str, body: dict, session: Session = Depends(get_session)) -> dict:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="unknown workspace id")
```

to:

```python
def send_request(workspace_id: str, body: dict, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)) -> dict:
    workspace = get_owned_workspace(workspace_id, current_user, session)
```

In `list_requests`, change:

```python
def list_requests(workspace_id: str, session: Session = Depends(get_session)) -> list[dict]:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="unknown workspace id")
```

to:

```python
def list_requests(workspace_id: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)) -> list[dict]:
    workspace = get_owned_workspace(workspace_id, current_user, session)
```

In `node_history`, change:

```python
def node_history(workspace_id: str, node_id: str, session: Session = Depends(get_session)) -> list[dict]:
    node = session.get(Node, node_id)
    if node is None or node.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="unknown node id")
```

to:

```python
def node_history(workspace_id: str, node_id: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)) -> list[dict]:
    get_owned_workspace(workspace_id, current_user, session)  # 404s before even checking the node exists, if the workspace isn't the caller's
    node = session.get(Node, node_id)
    if node is None or node.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="unknown node id")
```

- [ ] **Step 3: Update `tests/test_workspace_routes.py`**

The current top of this file reads:

```python
import json
import socket
from pathlib import Path

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app
```

Change it to:

```python
import json
import socket
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import User
from tests.conftest import login_as
```

Then add this fixture right after the `client = TestClient(app)` / `FIXTURE = ...` lines already in the file, before the first test function:

```python
@pytest.fixture(autouse=True)
def _authenticated():
    session = SessionLocal()
    try:
        user = User(github_id="test-github-id", username="testuser")
        session.add(user)
        session.commit()
        user_id = user.id
    finally:
        session.close()
    login_as(client, user_id)
```

This fixture runs automatically before every test in the file (matching
the `autouse=True` pattern `conftest.py`'s own `clean_db` fixture already
uses) and needs no per-test changes beyond this one addition — every
existing test in this file already uses the same top-level `client`
`TestClient` instance, which this fixture authenticates before each test
runs.

- [ ] **Step 4: Update `tests/test_request_routes.py`**

This file already imports `SessionLocal`, `Node`, `Request`, and
`Response as ResponseModel` (added in an earlier phase) — do not
duplicate or remove any of those. The current top of this file reads:

```python
import json
import socket
from pathlib import Path

import httpx
import respx
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Node, Request
from app.models import Response as ResponseModel
```

Change it to:

```python
import json
import socket
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Node, Request, User
from app.models import Response as ResponseModel
from tests.conftest import login_as
```

(Only three things changed: `pytest` added to the third import group,
`User` added to the `Node, Request` line, and the new `login_as` import
line added at the end — `Response as ResponseModel`'s own line is
untouched.)

Then add the identical `_authenticated` fixture from Step 3 (same code,
same reasoning) to this file too, in the same position (right after the
`client = TestClient(app)` / `FIXTURE = ...` lines, before the first test
function).

- [ ] **Step 5: Run the tests**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all pass — report the real total.

Run one adversarial check by hand to confirm the ownership boundary is real, not just re-pointed:

```bash
cd backend && .venv/bin/python -c "
from fastapi.testclient import TestClient
from app.main import app
from app.models import User
from app.db import SessionLocal
from tests.conftest import login_as
import json

client_a = TestClient(app)
client_b = TestClient(app)

session = SessionLocal()
user_a = User(github_id='a', username='alice'); session.add(user_a)
user_b = User(github_id='b', username='bob'); session.add(user_b)
session.commit()
login_as(client_a, user_a.id)
login_as(client_b, user_b.id)

ws = client_a.post('/api/workspaces', json={'name': 'alices', 'schema_kind': 'openapi', 'raw_schema': {'openapi': '3.0.0', 'info': {'title': 't', 'version': '1'}, 'paths': {}}}).json()
print('alice can see her own workspace:', client_a.get(f'/api/workspaces/{ws[\"id\"]}').status_code)
print('bob CANNOT see alices workspace:', client_b.get(f'/api/workspaces/{ws[\"id\"]}').status_code)
"
```

Expected: `200` then `404` — confirm this by hand before moving on; this is the real behavior this whole task exists to deliver.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/workspaces.py backend/app/routes/requests.py \
        backend/tests/test_workspace_routes.py backend/tests/test_request_routes.py
git commit -m "feat: enforce real per-user workspace ownership on every route"
```

---

### Task 3: Frontend auth gate

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Produces: `getCurrentUser(): Promise<CurrentUser | null>`, `logout(): Promise<void>`, `GITHUB_LOGIN_URL` (a plain string href, not a fetch call — it's a real page navigation to the backend, which redirects to GitHub) in `api.ts`.

- [ ] **Step 1: Add auth functions to `api.ts`**

Add this interface and these three exports near the top of the file, after the existing interfaces:

```typescript
export interface CurrentUser {
  id: string
  username: string
}

export const GITHUB_LOGIN_URL = '/api/auth/github/login'

export function getCurrentUser(): Promise<CurrentUser | null> {
  return fetch('/api/auth/me', { credentials: 'include' }).then((res) => {
    if (res.status === 401) return null
    return json<CurrentUser>(res)
  })
}

export function logout(): Promise<void> {
  return fetch('/api/auth/logout', { method: 'POST', credentials: 'include' }).then(() => undefined)
}
```

Then add `credentials: 'include'` to every one of the 6 remaining
EXISTING `fetch(...)` calls in this file — this is a no-op in same-origin
dev (the Vite proxy already makes these same-origin) but is required for
a real cross-origin deploy (frontend and backend on different real
domains, this phase's own stated deploy-readiness goal). Exact
before/after for each:

`createWorkspace`, change:

```typescript
  return fetch('/api/workspaces', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then((res) => json<{ id: string; name: string; schema_kind: string; node_count: number }>(res))
```

to:

```typescript
  return fetch('/api/workspaces', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    credentials: 'include',
  }).then((res) => json<{ id: string; name: string; schema_kind: string; node_count: number }>(res))
```

`listWorkspaces`, change:

```typescript
export function listWorkspaces(): Promise<WorkspaceSummary[]> {
  return fetch('/api/workspaces').then((res) => json<WorkspaceSummary[]>(res))
}
```

to:

```typescript
export function listWorkspaces(): Promise<WorkspaceSummary[]> {
  return fetch('/api/workspaces', { credentials: 'include' }).then((res) => json<WorkspaceSummary[]>(res))
}
```

`getWorkspace`, change:

```typescript
export function getWorkspace(id: string): Promise<Workspace> {
  return fetch(`/api/workspaces/${encodeURIComponent(id)}`).then((res) => json<Workspace>(res))
}
```

to:

```typescript
export function getWorkspace(id: string): Promise<Workspace> {
  return fetch(`/api/workspaces/${encodeURIComponent(id)}`, { credentials: 'include' }).then((res) => json<Workspace>(res))
}
```

`sendRequest`, change:

```typescript
  return fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/requests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ method, url, headers, body }),
  }).then((res) => json<SendResult>(res))
```

to:

```typescript
  return fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/requests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ method, url, headers, body }),
    credentials: 'include',
  }).then((res) => json<SendResult>(res))
```

`curlParse`, change:

```typescript
  return fetch('/api/curl-parse', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ curl }),
  }).then((res) => json<CurlParseResult>(res))
```

to:

```typescript
  return fetch('/api/curl-parse', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ curl }),
    credentials: 'include',
  }).then((res) => json<CurlParseResult>(res))
```

`getNodeHistory`, change:

```typescript
export function getNodeHistory(workspaceId: string, nodeId: string): Promise<NodeHistoryEntry[]> {
  return fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/nodes/${encodeURIComponent(nodeId)}/history`)
    .then((res) => json<NodeHistoryEntry[]>(res))
}
```

to:

```typescript
export function getNodeHistory(workspaceId: string, nodeId: string): Promise<NodeHistoryEntry[]> {
  return fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/nodes/${encodeURIComponent(nodeId)}/history`, { credentials: 'include' })
    .then((res) => json<NodeHistoryEntry[]>(res))
}
```

`getWorkspaceRequests`, change:

```typescript
export function getWorkspaceRequests(workspaceId: string): Promise<RequestHistoryEntry[]> {
  return fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/requests`)
    .then((res) => json<RequestHistoryEntry[]>(res))
}
```

to:

```typescript
export function getWorkspaceRequests(workspaceId: string): Promise<RequestHistoryEntry[]> {
  return fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/requests`, { credentials: 'include' })
    .then((res) => json<RequestHistoryEntry[]>(res))
}
```

- [ ] **Step 2: Add the auth gate to `App.tsx`**

Add to the imports:

```typescript
import { createWorkspace, getCurrentUser, getWorkspace, logout, type CurrentUser, type SendResult, type Workspace, GITHUB_LOGIN_URL } from './api'
```

(replacing the existing `import { createWorkspace, getWorkspace, type SendResult, type Workspace } from './api'` line).

Add `useEffect` to the React import:

```typescript
import { useCallback, useEffect, useState } from 'react'
```

Add this state, alongside the existing ones:

```typescript
  const [currentUser, setCurrentUser] = useState<CurrentUser | null | undefined>(undefined)
```

Add this effect right after the state declarations:

```typescript
  useEffect(() => {
    getCurrentUser().then(setCurrentUser).catch(() => setCurrentUser(null))
  }, [])
```

Add this handler, alongside the other handler functions:

```typescript
  function handleLogout() {
    logout().then(() => setCurrentUser(null))
  }
```

Right before the component's final `return (`, add these two early returns (after all the existing hook calls, before any JSX):

```tsx
  if (currentUser === undefined) {
    return <div className="app auth-loading">Loading…</div>
  }

  if (currentUser === null) {
    return (
      <div className="app auth-gate">
        <div className="brand">parity<span>.</span></div>
        <a className="auth-gate__button" href={GITHUB_LOGIN_URL}>Sign in with GitHub</a>
      </div>
    )
  }
```

Finally, add a small user badge + logout button to the existing `.hud-top` JSX, right after the `.brand` div and before `<WorkspaceList .../>`:

```tsx
          <span className="auth-user">{currentUser.username}</span>
          <button type="button" className="auth-logout" onClick={handleLogout}>Log out</button>
```

- [ ] **Step 3: Style the auth gate and badge**

Append to `frontend/src/styles.css`:

```css
.auth-loading{display:flex;align-items:center;justify-content:center;height:100vh;
  font-family:var(--mono);font-size:12px;color:var(--mute)}
.auth-gate{display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:24px;height:100vh}
.auth-gate__button{background:transparent;border:1px solid var(--match);color:var(--match);
  font-family:var(--mono);font-size:12px;padding:12px 24px;border-radius:2px;
  text-decoration:none;cursor:pointer}
.auth-gate__button:hover{background:var(--match);color:var(--ink)}
.auth-user{font-family:var(--mono);font-size:11px;color:var(--mute);margin-left:16px}
.auth-logout{background:transparent;border:1px solid var(--hair);color:var(--mute);
  font-family:var(--mono);font-size:10px;padding:9px 16px;border-radius:2px;cursor:pointer;margin-left:8px}
.auth-logout:hover{border-color:var(--violate);color:var(--violate)}
```

- [ ] **Step 4: Run the checks**

Run: `cd frontend && npx vitest run`
Expected: 15 passed (unchanged — no test files touched this task; the auth gate is a stateful/effectful top-level component, matching this codebase's own established precedent of no direct tests for that category).

Run: `cd frontend && npx tsc -b`
Expected: no errors.

Run: `cd frontend && npx vite build`
Expected: succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api.ts frontend/src/App.tsx frontend/src/styles.css
git commit -m "feat: frontend GitHub OAuth gate"
```

---

### Task 4: Setup instructions + everything-but-the-human-click verification

**Files:**
- Create: `AUTH_SETUP.md`
- Modify: `HANDOFF.md`

**Interfaces:**
- Consumes: Tasks 1-3's complete, committed changes. No new interfaces — this task verifies what's automatable and documents the one manual step this plan cannot perform on the user's behalf.

- [ ] **Step 1: Write `AUTH_SETUP.md`**

```markdown
# Setting up real GitHub OAuth for parity

Registering a GitHub OAuth App requires your own GitHub account — this is
the one step in Phase 3a that can't be automated.

## 1. Register the app

1. Go to <https://github.com/settings/developers> → **OAuth Apps** → **New OAuth App**.
2. **Application name**: `parity (dev)` (anything you like — it's only shown on GitHub's consent screen).
3. **Homepage URL**: `http://localhost:5173`
4. **Authorization callback URL**: `http://localhost:8123/api/auth/github/callback`
   — this must match `GITHUB_CALLBACK_URL` below *exactly*, including the port.
5. Click **Register application**.
6. Copy the **Client ID**.
7. Click **Generate a new client secret**, copy it immediately (GitHub only shows it once).

## 2. Set the real environment variables

Before starting the backend, export these (or add them to however you already set `DATABASE_URL`):

```bash
export GITHUB_CLIENT_ID="<the real client id from step 1>"
export GITHUB_CLIENT_SECRET="<the real client secret from step 1>"
export GITHUB_CALLBACK_URL="http://localhost:8123/api/auth/github/callback"
export SESSION_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export FRONTEND_ORIGIN="http://localhost:5173"
```

`SESSION_SECRET_KEY` signs the session cookie — generate a real random
one (the command above does this for you); never reuse the app's own
`dev-only-insecure-secret-change-before-any-real-deploy` default outside
local dev with no real OAuth app registered.

## 3. Run it and sign in for real

```bash
cd backend && docker compose up -d
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/alembic upgrade head
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/uvicorn app.main:app --port 8123

cd frontend && npm run dev
```

Open `http://localhost:5173`, click **Sign in with GitHub**, approve the
real consent screen, and confirm you land back in the app with your real
GitHub username showing in the top bar.
```

- [ ] **Step 2: Verify everything that's automatable without a registered app**

Start the real stack WITHOUT setting the real GitHub env vars (using
only the dev defaults already baked into the code):

```bash
cd backend
docker compose up -d
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/alembic upgrade head
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" GITHUB_CLIENT_ID=dev GITHUB_CLIENT_SECRET=dev GITHUB_CALLBACK_URL=http://localhost:8123/api/auth/github/callback .venv/bin/uvicorn app.main:app --port 8123 &
cd ../frontend && npm run dev &
```

In a real browser, confirm:
- The app shows the "Sign in with GitHub" gate on first load (not the
  workspace UI) — this proves the frontend correctly treats "no session"
  as logged-out.
- Clicking "Sign in with GitHub" navigates to a real `github.com/login/oauth/authorize`
  URL with `client_id=dev` in the query string (confirming the redirect
  really fires — do NOT attempt to complete a real GitHub login with
  fake credentials; just confirm the redirect happens and stop there).
- A direct `curl http://localhost:8123/api/workspaces` (no cookie) returns
  `401`, not the old fixed-user workspace list — the real enforcement
  Task 2 added.

Run the full automated suite one more time: `cd backend && .venv/bin/python -m pytest -q`
(expect the real total from Task 2's own run) and `cd frontend && npx vitest run` (expect 15).

Stop the background uvicorn/vite processes when done; leave Postgres running.

- [ ] **Step 3: Update `HANDOFF.md`**

Append a new `## Phase 3a: Real GitHub OAuth + Per-User Workspaces`
section, following the existing sections' structure. State plainly:
- The real OAuth flow, the session mechanism (Starlette `SessionMiddleware`,
  a signed cookie — not a server-side store), and that every
  workspace-scoped route now genuinely enforces ownership (not just
  records an owner nobody checks) — cite the adversarial two-user check
  from Task 2's Step 5 as real, verified evidence.
- The one manual step this plan could not perform: a human must
  register a real GitHub OAuth App and complete one real login to fully
  verify the flow end to end — point to `AUTH_SETUP.md` for exact steps,
  and state clearly that this has NOT yet been done (don't imply full
  end-to-end verification happened if it didn't).
- The real test counts (confirm the actual final numbers from Task 2's
  `pytest -q` output and Task 3's `vitest run` output).
- Existing dev-DB workspaces (owned by the old fixed default user) are
  explicitly still there, unreassigned, by deliberate ruling (no real
  user data existed to migrate) — anyone testing locally with old
  workspace data won't see it once they log in for real, since it's
  scoped to a different user id than any real GitHub account will ever
  have. This is expected, not a bug.
- Next: Phase 3b (encrypted per-workspace credential storage) and Phase
  3c (visual identity final pass + deploy-readiness).

- [ ] **Step 4: Commit**

```bash
git add AUTH_SETUP.md HANDOFF.md
git commit -m "docs: Phase 3a HANDOFF + real GitHub OAuth setup instructions"
```
