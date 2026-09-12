# Phase 3b: Encrypted Per-Workspace Credential Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user store a real credential (an API key, a bearer token) for a workspace so it doesn't have to be pasted into every curl/request builder session by hand — Fernet-encrypted at rest (SPEC.md §7.4), and actually used when firing a real request against that workspace.

**Architecture:** `Workspace.encrypted_credential` (a `bytea` column, already real since Phase 1a's original migration — never used until now) stores a Fernet-encrypted value; a new `Workspace.credential_header_name` column (plaintext — header names aren't sensitive) records which header it goes in. This two-column split exists for a real, verified reason: the project's own reference fixture (Petstore) authenticates via a custom `api_key` header, not `Authorization` — a design that only supported `Authorization` would fail on the exact API this whole project tests against. `app/crypto.py` holds the encrypt/decrypt primitives, keyed by a new required `FERNET_KEY` env var (added to `app/main.py`'s existing startup validation from Phase 3a, so a missing key fails at boot, not on first credential save). `send_request` injects the decrypted credential into the outbound request's headers if the user's own supplied headers don't already set that same header — and, a real gap caught during this plan's own self-review, the injected value is explicitly redacted before persisting to `Request.headers`, regardless of what header name the user chose (the existing `redact_headers` helper's fixed name list wouldn't catch a custom header name on its own).

**Tech Stack:** `cryptography` (new — SPEC.md's own named choice, "Fernet (symmetric, from the cryptography package)", verified installed and working below: key generation, encrypt/decrypt round trip, and wrong-key rejection all confirmed against the real library).

**Spec:** [`SPEC.md`](../../../SPEC.md) §7.4 (the exact stated design: Fernet, keyed by a server-held secret, "defends against a database dump, not a full secrets-manager setup — stated plainly, not implied as more than it is"), §7.5 (`workspace.encrypted_credential`, already in the schema since Phase 1a), §12 (rotating the key invalidates every stored credential — a real operational fact worth documenting again for Phase 3c's deploy).

## Global Constraints

- **Verified against the real installed `cryptography` library (2026-09-12), not assumed:** `Fernet.generate_key()` produces a real 44-byte urlsafe-base64 key; `Fernet(key).encrypt(value.encode())` / `.decrypt(token)` round-trip correctly; decrypting with the wrong key raises `cryptography.fernet.InvalidToken`, not a silent wrong answer; a key read back from a plain environment-variable string (encode/decode round trip) works identically to the raw bytes GitHub — a real concern since `FERNET_KEY` is an env var, necessarily a string.
- **`FERNET_KEY` has no default and is required at boot, in every environment (dev included)** — unlike `SESSION_SECRET_KEY`'s dev-default (a fixed insecure string still usable as a session-signing secret), a Fernet key must be a real, correctly-formatted key or every encrypt/decrypt call fails outright; there is no safe "fake but working" default to fall back to. A silently-auto-generated key on every process restart would also make every previously-stored credential permanently undecryptable the moment the process restarts — worse than requiring the user to set one explicitly. `AUTH_SETUP.md` gets a short addition with the exact one-line command to generate one for local dev.
- **A real security gap found and closed during this plan's own self-review, not left for a task review to catch**: the existing `redact_headers` helper (Phase 2a) only redacts a fixed set of known header names. A user-chosen credential header name (e.g. `api_key`, matching the project's own Petstore fixture) is NOT in that fixed set, so persisting the request's headers verbatim after redaction would still write the real decrypted secret to the database. The route that fires a request explicitly redacts whatever header the credential was injected into, on top of the existing fixed-set redaction — this is stated as its own step below, not folded silently into `redact_headers` itself (which has no way to know a workspace's per-request credential header name).
- **Injection never overrides a header the user's own request already set** — if the user's own headers already include the same header name (case-insensitive) as the stored credential, their value wins. The stored credential is a convenience default, not a forced override.

---

### Task 1: Encryption + storage + injection (backend)

**Files:**
- Create: `backend/app/crypto.py`
- Modify: `backend/app/models.py` (add `Workspace.credential_header_name`)
- Modify: `backend/app/main.py` (add `FERNET_KEY` to the required-env-var check)
- Modify: `backend/app/routes/workspaces.py` (the two new credential routes, expose credential state in `get_workspace`)
- Modify: `backend/app/routes/requests.py` (injection + the explicit redaction fix)
- Modify: `backend/pyproject.toml` (add `cryptography`)
- Modify: `backend/tests/conftest.py` (set a real, fixed `FERNET_KEY` for tests, matching the existing pattern for `SESSION_SECRET_KEY`/`GITHUB_CLIENT_ID`)
- Test: `backend/tests/test_crypto.py`
- Test: `backend/tests/test_workspace_routes.py` (the two new routes)
- Test: `backend/tests/test_request_routes.py` (injection + redaction)
- Create: `backend/alembic/versions/<autogenerated>.py`

**Interfaces:**
- Produces: `encrypt_credential(value: str) -> bytes`, `decrypt_credential(token: bytes) -> str`, `class CredentialDecryptionError(Exception)` in `app.crypto`. `Workspace.credential_header_name: str | None`.

- [ ] **Step 1: Add the dependency**

In `backend/pyproject.toml`, add `"cryptography>=42.0"` to the `dependencies` list.

Run: `cd backend && .venv/bin/pip install -e ".[dev]"`
Expected: installs `cryptography` with no errors.

- [ ] **Step 2: Write `app/crypto.py`**

```python
"""Fernet-encrypted at-rest storage for target-API credentials
(SPEC.md §7.4): defends against a database dump, not a full
secrets-manager setup -- stated plainly, not implied as more than it is.
Keyed by a server-held secret from the environment (FERNET_KEY),
generated once, never rotated casually (SPEC.md §12: a rotation
invalidates every already-stored credential -- there is no "re-encrypt
everything" migration path here, by design, matching the stated scope)."""

from __future__ import annotations

import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken


class CredentialDecryptionError(Exception):
    pass


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = os.environ["FERNET_KEY"]
    return Fernet(key.encode("utf-8"))


def encrypt_credential(value: str) -> bytes:
    return _fernet().encrypt(value.encode("utf-8"))


def decrypt_credential(token: bytes) -> str:
    try:
        return _fernet().decrypt(token).decode("utf-8")
    except InvalidToken as exc:
        raise CredentialDecryptionError(
            "stored credential could not be decrypted (wrong or rotated FERNET_KEY?)"
        ) from exc
```

- [ ] **Step 3: Write `tests/test_crypto.py`**

```python
import pytest

from app.crypto import CredentialDecryptionError, decrypt_credential, encrypt_credential


def test_encrypt_then_decrypt_round_trips():
    token = encrypt_credential("sk_live_real_looking_secret_value")
    assert decrypt_credential(token) == "sk_live_real_looking_secret_value"


def test_encrypted_value_does_not_contain_the_plaintext():
    token = encrypt_credential("a-very-specific-secret-string")
    assert b"a-very-specific-secret-string" not in token


def test_a_corrupted_token_fails_to_decrypt():
    token = encrypt_credential("x")
    corrupted = token[:-4] + b"gggg"
    with pytest.raises(CredentialDecryptionError):
        decrypt_credential(corrupted)
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_crypto.py -v`
Expected: all 3 pass. (This requires `FERNET_KEY` to be set — Step 8 below adds it to `conftest.py`; if you run this file in isolation before that step, set it yourself: `FERNET_KEY=$(.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())') .venv/bin/python -m pytest tests/test_crypto.py -v`.)

- [ ] **Step 5: Add `Workspace.credential_header_name` and the migration**

In `backend/app/models.py`, add this line to the `Workspace` class, right after `encrypted_credential`:

```python
    credential_header_name: Mapped[str | None] = mapped_column(String, nullable=True)  # e.g. "Authorization" or "api_key" -- SPEC.md §7.4
```

Run:

```bash
cd backend
docker compose up -d
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/alembic revision --autogenerate -m "add workspace.credential_header_name"
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/alembic upgrade head
```

This is a plain nullable column addition (no default needed, unlike `base_path`'s earlier migration — a nullable column with no default is always safe to add to a non-empty table, since existing rows simply get `NULL`). Read the generated migration file and confirm it's exactly `op.add_column('workspace', sa.Column('credential_header_name', sa.String(), nullable=True))` with a matching `downgrade()` — no `server_default` needed here.

- [ ] **Step 6: Require `FERNET_KEY` at boot**

In `backend/app/main.py`, change:

```python
for _required_var in ("GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "GITHUB_CALLBACK_URL"):
    if os.environ.get(_required_var) is None:
        raise RuntimeError(f"{_required_var} is required (see AUTH_SETUP.md) -- refusing to boot without it")
```

to:

```python
for _required_var in ("GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "GITHUB_CALLBACK_URL", "FERNET_KEY"):
    if os.environ.get(_required_var) is None:
        raise RuntimeError(f"{_required_var} is required (see AUTH_SETUP.md) -- refusing to boot without it")
```

- [ ] **Step 7: Add the two credential routes and expose credential state**

In `backend/app/routes/workspaces.py`, add this import:

```python
from app.crypto import encrypt_credential
```

Add these two routes at the end of the file:

```python
@router.put("/{workspace_id}/credential")
def set_credential(workspace_id: str, body: dict, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)) -> dict:
    workspace = get_owned_workspace(workspace_id, current_user, session)
    header_name = body.get("header_name")
    value = body.get("value")
    if not header_name or not value:
        raise HTTPException(status_code=422, detail="header_name and value are required")
    workspace.credential_header_name = header_name
    workspace.encrypted_credential = encrypt_credential(value)
    session.commit()
    return {"status": "ok"}


@router.delete("/{workspace_id}/credential")
def clear_credential(workspace_id: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)) -> dict:
    workspace = get_owned_workspace(workspace_id, current_user, session)
    workspace.credential_header_name = None
    workspace.encrypted_credential = None
    session.commit()
    return {"status": "ok"}
```

In `get_workspace`, change the return statement from:

```python
    return {
        "id": workspace.id, "name": workspace.name, "schema_kind": workspace.schema_kind,
        "base_path": workspace.base_path, "schema_source": workspace.schema_source,
        "nodes": node_dicts,
        "edges": [{"from_node": a, "to_node": b} for a, b in edges],
    }
```

to:

```python
    return {
        "id": workspace.id, "name": workspace.name, "schema_kind": workspace.schema_kind,
        "base_path": workspace.base_path, "schema_source": workspace.schema_source,
        "has_credential": workspace.encrypted_credential is not None,
        "credential_header_name": workspace.credential_header_name,
        "nodes": node_dicts,
        "edges": [{"from_node": a, "to_node": b} for a, b in edges],
    }
```

(The real decrypted value is never returned by any route -- once saved, it's write-only, matching the same "never displayed again" convention real secret-manager UIs use. `credential_header_name` is exposed because it isn't sensitive and the frontend needs it to show which header is currently configured.)

- [ ] **Step 8: Wire injection + redaction into `send_request`**

In `backend/tests/conftest.py`, add this line alongside the existing `os.environ.setdefault(...)` calls near the top of the file:

```python
os.environ.setdefault("FERNET_KEY", "L3RY_MnUUvW0V0jjkBaLpN7RB1P_yBc-K4jSAG6ZmA0=")
```

(This is a real, validly-formatted Fernet key -- generated once for this test suite's own fixed use, not a placeholder string. It is not used anywhere else and has no bearing on any real deployment's own `FERNET_KEY`.)

In `backend/app/routes/requests.py`, add this import:

```python
from app.crypto import CredentialDecryptionError, decrypt_credential
```

Change:

```python
    method = body.get("method")
    url = body.get("url")
    headers = body.get("headers") or {}
    req_body = body.get("body")
    if not method or not url:
        raise HTTPException(status_code=422, detail="method and url are required")
    if req_body is not None and not isinstance(req_body, str):
        raise HTTPException(status_code=422, detail="body must be a string or null")

    try:
        resp, latency_ms = fire_request(method, url, headers, req_body)
    except ProxyError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
```

to:

```python
    method = body.get("method")
    url = body.get("url")
    headers = body.get("headers") or {}
    req_body = body.get("body")
    if not method or not url:
        raise HTTPException(status_code=422, detail="method and url are required")
    if req_body is not None and not isinstance(req_body, str):
        raise HTTPException(status_code=422, detail="body must be a string or null")

    if workspace.encrypted_credential and workspace.credential_header_name:
        if not any(h.lower() == workspace.credential_header_name.lower() for h in headers):
            try:
                headers = {**headers, workspace.credential_header_name: decrypt_credential(workspace.encrypted_credential)}
            except CredentialDecryptionError as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        resp, latency_ms = fire_request(method, url, headers, req_body)
    except ProxyError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
```

Then change the `request_row` construction from:

```python
    request_row = Request(
        workspace_id=workspace.id, node_id=node.id if node else None,
        method=method.upper(), url=url, headers=redact_headers(headers), body=req_body,
    )
```

to:

```python
    persisted_headers = redact_headers(headers)
    if workspace.credential_header_name:
        # redact_headers only knows a fixed set of well-known header
        # names -- a user-chosen credential header (e.g. the project's
        # own Petstore fixture uses "api_key", not "Authorization") isn't
        # in that set, so it must be explicitly redacted here too, or the
        # real decrypted secret would be written to the database
        # verbatim (a real gap found and closed during this plan's own
        # self-review, not left for a task review to catch).
        for _key in list(persisted_headers):
            if _key.lower() == workspace.credential_header_name.lower():
                persisted_headers[_key] = "[REDACTED]"

    request_row = Request(
        workspace_id=workspace.id, node_id=node.id if node else None,
        method=method.upper(), url=url, headers=persisted_headers, body=req_body,
    )
```

- [ ] **Step 9: Add tests to `tests/test_workspace_routes.py`**

```python
def test_set_and_clear_a_credential():
    ws = client.post("/api/workspaces", json={
        "name": "x", "schema_kind": "openapi",
        "raw_schema": {"openapi": "3.0.0", "info": {"title": "t", "version": "1"}, "paths": {}},
    }).json()

    r = client.put(f"/api/workspaces/{ws['id']}/credential", json={"header_name": "api_key", "value": "sk_test_123"})
    assert r.status_code == 200

    got = client.get(f"/api/workspaces/{ws['id']}").json()
    assert got["has_credential"] is True
    assert got["credential_header_name"] == "api_key"

    r2 = client.delete(f"/api/workspaces/{ws['id']}/credential")
    assert r2.status_code == 200

    got2 = client.get(f"/api/workspaces/{ws['id']}").json()
    assert got2["has_credential"] is False
    assert got2["credential_header_name"] is None


def test_set_credential_requires_both_fields():
    ws = client.post("/api/workspaces", json={
        "name": "x", "schema_kind": "openapi",
        "raw_schema": {"openapi": "3.0.0", "info": {"title": "t", "version": "1"}, "paths": {}},
    }).json()
    r = client.put(f"/api/workspaces/{ws['id']}/credential", json={"header_name": "api_key"})
    assert r.status_code == 422


def test_workspace_without_a_credential_reports_it_honestly():
    ws = client.post("/api/workspaces", json={
        "name": "x", "schema_kind": "openapi",
        "raw_schema": {"openapi": "3.0.0", "info": {"title": "t", "version": "1"}, "paths": {}},
    }).json()
    got = client.get(f"/api/workspaces/{ws['id']}").json()
    assert got["has_credential"] is False
    assert got["credential_header_name"] is None
```

- [ ] **Step 10: Add tests to `tests/test_request_routes.py`**

```python
@respx.mock
def test_a_stored_credential_is_injected_and_redacted(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Petstore", "schema_kind": "openapi", "raw_schema": FIXTURE,
    }).json()
    client.put(f"/api/workspaces/{ws['id']}/credential", json={"header_name": "api_key", "value": "sk_real_secret_value"})

    route = respx.get("https://93.184.216.34/api/v3/pet/1").mock(
        return_value=httpx.Response(200, json={"id": 1, "name": "Fido", "photoUrls": []})
    )
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "GET", "url": "https://example.invalid/api/v3/pet/1", "headers": {}, "body": None,
    })
    assert r.status_code == 201

    # the real outbound request must have received the REAL decrypted value
    sent_headers = route.calls.last.request.headers
    assert sent_headers["api_key"] == "sk_real_secret_value"

    # but the persisted row must never contain the real value
    from app.db import SessionLocal
    from app.models import Request as RequestModel
    session = SessionLocal()
    try:
        req_row = session.query(RequestModel).filter(RequestModel.workspace_id == ws["id"]).one()
        assert req_row.headers.get("api_key") == "[REDACTED]"
    finally:
        session.close()


@respx.mock
def test_a_users_own_header_wins_over_the_stored_credential(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Petstore", "schema_kind": "openapi", "raw_schema": FIXTURE,
    }).json()
    client.put(f"/api/workspaces/{ws['id']}/credential", json={"header_name": "api_key", "value": "stored-secret"})

    route = respx.get("https://93.184.216.34/api/v3/pet/1").mock(
        return_value=httpx.Response(200, json={"id": 1, "name": "Fido", "photoUrls": []})
    )
    client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "GET", "url": "https://example.invalid/api/v3/pet/1",
        "headers": {"api_key": "user-supplied-value"}, "body": None,
    })
    sent_headers = route.calls.last.request.headers
    assert sent_headers["api_key"] == "user-supplied-value"
```

- [ ] **Step 11: Run the tests**

Run: `cd backend && docker compose up -d && .venv/bin/python -m pytest -q`
Expected: all pass — report the real total (124 prior + 3 crypto + 3 workspace-credential + 2 request-injection = 132; confirm the real number).

- [ ] **Step 12: Commit**

```bash
git add backend/app/crypto.py backend/app/models.py backend/app/main.py \
        backend/app/routes/workspaces.py backend/app/routes/requests.py \
        backend/pyproject.toml backend/tests/conftest.py \
        backend/tests/test_crypto.py backend/tests/test_workspace_routes.py backend/tests/test_request_routes.py \
        backend/alembic/versions/
git commit -m "feat: encrypted per-workspace credential storage (SPEC.md §7.4)"
```

---

### Task 2: Credential UI (frontend)

**Files:**
- Modify: `frontend/src/api.ts`
- Create: `frontend/src/components/CredentialPanel.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Produces: `setCredential(workspaceId: string, headerName: string, value: string): Promise<void>`, `clearCredential(workspaceId: string): Promise<void>` in `api.ts`. `<CredentialPanel workspace={Workspace} onClose={() => void} onSaved={(ws: Workspace) => void} />`.

- [ ] **Step 1: Widen `Workspace` and add the two API functions**

In `frontend/src/api.ts`, change:

```typescript
export interface Workspace {
  id: string
  name: string
  schema_kind: 'openapi' | 'graphql'
  base_path: string
  schema_source: string
  nodes: Node[]
  edges: Edge[]
}
```

to:

```typescript
export interface Workspace {
  id: string
  name: string
  schema_kind: 'openapi' | 'graphql'
  base_path: string
  schema_source: string
  has_credential: boolean
  credential_header_name: string | null
  nodes: Node[]
  edges: Edge[]
}
```

Add these two functions at the end of the file:

```typescript
export function setCredential(workspaceId: string, headerName: string, value: string): Promise<void> {
  return fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/credential`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ header_name: headerName, value }),
    credentials: 'include',
  }).then((res) => json<{ status: string }>(res)).then(() => undefined)
}

export function clearCredential(workspaceId: string): Promise<void> {
  return fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/credential`, {
    method: 'DELETE',
    credentials: 'include',
  }).then((res) => json<{ status: string }>(res)).then(() => undefined)
}
```

- [ ] **Step 2: Create `components/CredentialPanel.tsx`**

```tsx
import { useState } from 'react'
import { clearCredential, setCredential, type Workspace } from '../api'
import { useModalPanel } from '../lib/useModalPanel'

/** A write-only credential form: once saved, the real value is never
 * shown again (matching real secret-manager UI conventions) -- only
 * whether one is currently set, and under which header name. */
export function CredentialPanel({ workspace, onClose, onSaved }: {
  workspace: Workspace
  onClose: () => void
  onSaved: (workspace: Workspace) => void
}) {
  const closeRef = useModalPanel(true, onClose)
  const [headerName, setHeaderName] = useState(workspace.credential_header_name ?? 'Authorization')
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSave() {
    setBusy(true)
    setError(null)
    try {
      await setCredential(workspace.id, headerName, value)
      onSaved({ ...workspace, has_credential: true, credential_header_name: headerName })
      setValue('')
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  async function handleClear() {
    setBusy(true)
    setError(null)
    try {
      await clearCredential(workspace.id)
      onSaved({ ...workspace, has_credential: false, credential_header_name: null })
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="history-backdrop" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="history-panel" role="dialog" aria-modal="true" aria-label="Workspace credential">
        <button type="button" className="dive__close" onClick={onClose} ref={closeRef} aria-label="Close credential panel">Close ✕</button>
        <h3 className="dive__title">Credential</h3>

        <p className="dive__detail">
          {workspace.has_credential
            ? `A credential is stored for the "${workspace.credential_header_name}" header. Save a new value to replace it, or clear it below.`
            : 'No credential stored yet. It will be sent automatically on every request that doesn’t already set the same header.'}
        </p>

        <label className="credential-panel__label" htmlFor="credential-header-name">Header name</label>
        <input
          id="credential-header-name" type="text" value={headerName}
          onChange={(e) => setHeaderName(e.target.value)} disabled={busy}
        />

        <label className="credential-panel__label" htmlFor="credential-value">Value</label>
        <input
          id="credential-value" type="password" value={value} placeholder="Paste the real credential value"
          onChange={(e) => setValue(e.target.value)} disabled={busy}
        />

        {error && <p className="dive__detail" style={{ color: 'var(--violate)' }}>{error}</p>}

        <div className="credential-panel__actions">
          <button type="button" className="dive__send" onClick={handleSave} disabled={busy || !headerName.trim() || !value.trim()}>
            {busy ? 'Saving…' : 'Save'}
          </button>
          {workspace.has_credential && (
            <button type="button" className="history-toggle" onClick={handleClear} disabled={busy}>
              Clear stored credential
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Wire it into `App.tsx`**

Add the import:

```typescript
import { CredentialPanel } from './components/CredentialPanel'
```

Add state alongside the existing ones:

```typescript
  const [showCredential, setShowCredential] = useState(false)
```

Add a stable close handler alongside the other `useCallback`s:

```typescript
  const handleCloseCredential = useCallback(() => setShowCredential(false), [])
```

In the JSX, inside `.hud-top`, add a "Credential" toggle button right after the existing History button and before `<WorkspaceForm .../>` (matching the same `{workspace && (...)}` gating the History button already uses):

```tsx
          {workspace && (
            <button type="button" className="history-toggle" onClick={() => setShowCredential(true)}>
              Credential
            </button>
          )}
```

Right after the existing `{workspace && showHistory && (<HistoryPanel .../>)}` block, add:

```tsx
      {workspace && showCredential && (
        <CredentialPanel
          workspace={workspace}
          onClose={handleCloseCredential}
          onSaved={(updated) => setWorkspace(updated)}
        />
      )}
```

- [ ] **Step 4: Style the credential form**

Append to `frontend/src/styles.css`:

```css
.credential-panel__label{display:block;font-family:var(--mono);font-size:10px;color:var(--mute);
  margin:14px 0 4px}
.credential-panel__label:first-of-type{margin-top:0}
.credential-panel__actions{display:flex;gap:8px;margin-top:18px}
```

(`CredentialPanel`'s `<input>` elements reuse the existing `.history-panel input` cascade if one exists; if plain `<input>` inside `.history-panel` has no existing styling, add:)

```css
.history-panel input{width:100%;background:rgba(255,255,255,.04);border:1px solid var(--hair);
  color:var(--paper);font-family:var(--mono);font-size:11px;padding:9px 12px;border-radius:2px}
```

- [ ] **Step 5: Run the checks**

Run: `cd frontend && npx vitest run`
Expected: 15 passed (unchanged — no test files touched this task, matching this codebase's existing precedent of no direct tests for stateful/effectful components).

Run: `cd frontend && npx tsc -b`
Expected: no errors.

Run: `cd frontend && npx vite build`
Expected: succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api.ts frontend/src/components/CredentialPanel.tsx frontend/src/App.tsx frontend/src/styles.css
git commit -m "feat: workspace credential UI"
```

---

### Task 3: Live verification + `HANDOFF.md`

**Files:**
- Modify: `HANDOFF.md`
- Modify: `AUTH_SETUP.md`

**Interfaces:**
- Consumes: Tasks 1-2's complete, committed changes. No new interfaces — this task verifies and documents.

- [ ] **Step 1: Add `FERNET_KEY` generation to `AUTH_SETUP.md`**

Add a short new section to `AUTH_SETUP.md`, after its existing env-var section, giving the exact command to generate a real key:

```markdown
## Generating a FERNET_KEY (for encrypted credential storage, Phase 3b)

```bash
export FERNET_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

Like `SESSION_SECRET_KEY`, this is required at boot in every environment
(dev included) — there is no default. Unlike a session secret, rotating
this key permanently locks you out of any credential already stored
under the old one (SPEC.md §12) — generate it once and keep it, the same
discipline as any real secrets-manager key.
```

- [ ] **Step 2: Start the real stack and live-verify**

```bash
cd backend
docker compose up -d
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/alembic upgrade head
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" \
  GITHUB_CLIENT_ID=dev GITHUB_CLIENT_SECRET=dev GITHUB_CALLBACK_URL=http://localhost:8123/api/auth/github/callback \
  FERNET_KEY="$(.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
  .venv/bin/uvicorn app.main:app --port 8123 &
cd ../frontend && npm run dev &
```

No real GitHub app is registered in this environment yet (Phase 3a's own
HANDOFF names this as still the user's own step) — this task does NOT
attempt a real GitHub login. Instead, verify the real, end-to-end
backend pipeline over real HTTP (not pytest) using a manually-signed
session cookie, the same real technique this project's own test suite
already uses (`tests/conftest.py`'s `login_as` helper) — this exercises
the real running server, real Postgres, and real Fernet encryption, just
without a real GitHub round trip:

```bash
cd backend
.venv/bin/python -c "
import itsdangerous, base64, json
from app.db import SessionLocal
from app.models import User

session = SessionLocal()
user = User(github_id='live-verify', username='live-verify-user')
session.add(user)
session.commit()
user_id = user.id
session.close()

signer = itsdangerous.TimestampSigner('dev-only-insecure-secret-change-before-any-real-deploy')
payload = base64.b64encode(json.dumps({'user_id': user_id}).encode('utf-8'))
print(signer.sign(payload).decode('utf-8'))
"
```

Use the printed value as the `session` cookie in real `curl` calls
against the running server on port 8123:

```bash
COOKIE="session=<paste the printed value>"

# create a real workspace
curl -s -X POST http://127.0.0.1:8123/api/workspaces -b "$COOKIE" \
  -H 'Content-Type: application/json' \
  -d '{"name": "Petstore live", "schema_kind": "openapi", "schema_source_url": "https://petstore3.swagger.io/api/v3/openapi.json"}'
# note the returned "id"

# set a real credential
curl -s -X PUT http://127.0.0.1:8123/api/workspaces/<id>/credential -b "$COOKIE" \
  -H 'Content-Type: application/json' \
  -d '{"header_name": "api_key", "value": "live-verify-test-value"}'

# confirm it's reported, never the real value
curl -s http://127.0.0.1:8123/api/workspaces/<id> -b "$COOKIE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['has_credential'], d['credential_header_name'])"

# fire a real request against the real, live Petstore API -- a GET on
# this endpoint needs no real auth, so a fake credential value is fine
# for this purpose; the point is confirming the header gets sent and
# then redacted, not that Petstore accepts it
curl -s -X POST http://127.0.0.1:8123/api/workspaces/<id>/requests -b "$COOKIE" \
  -H 'Content-Type: application/json' \
  -d '{"method": "GET", "url": "https://petstore3.swagger.io/api/v3/pet/findByStatus?status=available", "headers": {}, "body": null}'

# confirm the credential was really injected + really redacted --
# inspect the persisted row directly, the same way Task 1's own tests do
.venv/bin/python -c "
from app.db import SessionLocal
from app.models import Request as RequestModel
session = SessionLocal()
row = session.query(RequestModel).order_by(RequestModel.sent_at.desc()).first()
print('persisted header value (must be [REDACTED]):', row.headers.get('api_key'))
"
```

Then, in a real browser, confirm what IS verifiable without a real
GitHub login (matching Phase 3a's own Task 4 pattern exactly): the app
shows the logged-out "Sign in with GitHub" gate on load, not the
workspace UI or a crash.

Run the real test suites yourself: `cd backend && .venv/bin/python -m pytest -q`
(confirm the real count from Task 1's own final run) and
`cd frontend && npx vitest run` (expect 15).

Stop the background uvicorn/vite processes when done; leave Postgres running.

- [ ] **Step 3: Update `HANDOFF.md`**

Append a new `## Phase 3b: Encrypted Per-Workspace Credential Storage`
section, following the existing sections' structure. State plainly:
- Real Fernet encryption, keyed by a required `FERNET_KEY` (no default,
  every environment) — a database dump alone can't recover a stored
  credential, matching SPEC.md §7.4's own stated (and stated-limited)
  security goal.
- The header-name/value split, and why (the project's own Petstore
  reference fixture uses a custom `api_key` header, not `Authorization`
  — a design that only supported one fixed header would fail on the
  exact API this whole project tests against).
- The real redaction gap found and closed during this plan's own
  self-review (a custom credential header name isn't in `redact_headers`'s
  fixed known-name set, so it needed its own explicit redaction step) —
  name this as a real, deliberate fix, not an afterthought.
- The real test counts (confirm the actual final numbers from Task 1's
  `pytest -q` output and Task 2's `vitest run` output).
- Whether full UI-driven live verification was completed (it needs a
  real GitHub login, same as Phase 3a) or whether this phase's
  verification stayed at the API-call level, same honesty discipline
  Phase 3a's Task 4 established — state exactly which was actually done.
- Next: Phase 3c (SPEC.md §8.2, §12) — the final visual-identity
  palette/type pass, and deploy-readiness (Dockerfile/`render.yaml`/env
  docs, plus resolving the deploy-topology decisions Phase 3a's own
  HANDOFF section named as still open: which real domains the frontend
  and backend will actually live on, and updating the frontend's
  currently-hardcoded relative `/api/...` paths accordingly).

- [ ] **Step 4: Commit**

```bash
git add HANDOFF.md AUTH_SETUP.md
git commit -m "docs: Phase 3b HANDOFF + FERNET_KEY setup instructions"
```
