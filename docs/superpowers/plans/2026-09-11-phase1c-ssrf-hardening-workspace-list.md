# Phase 1c: SSRF Pinning Hardening + Workspace List UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two parked findings from Phase 1b's final review before
starting Phase 2 — a CGNAT gap in the SSRF baseline guard and a
DNS-rebinding TOCTOU window between our own safety check and httpx's own
independent connection-time resolution — and ship the workspace-list/
picker UI gap that's been named-and-deferred since Phase 1a.

**Architecture:** The two schema-fetch functions (`fetch_spec`,
`fetch_introspection`) stop resolving-then-trusting-httpx-to-resolve-again
and instead resolve the target hostname themselves, validate every
resolved address, and connect directly to the validated IP while
preserving the original hostname as the `Host` header and TLS SNI/cert
hostname — closing the TOCTOU window a second independent resolution
would otherwise leave open. This consolidates into one shared primitive
(`send_pinned`) in `app/schema/openapi.py` that `app/schema/graphql.py`
reuses, replacing the now-retired `is_safe_url` (its one remaining job —
being a boolean pre-check — is subsumed by the pinning path itself, so
keeping it around as a second, now-unused, gate would just be dead code).
On the frontend, a small new component lists persisted workspaces and
loads the one a user picks.

**Tech Stack:** `httpx` (already a dependency) — specifically its
`extensions={"sni_hostname": ...}` request extension (verified against
the real installed `httpx==0.28.1` below) and `httpx.URL.copy_with(host=...)`
(verified to correctly rewrite the connection target while preserving
port/path/query and auto-bracketing IPv6, also below).

**Spec:** [`SPEC.md`](../../../SPEC.md) §7.3 (SSRF — the baseline this
phase closes a real gap in, while still deferring the fuller Phase-2
sandboxed-proxy mitigation for real request execution), §8.4 (the
frontend chrome's "workspace switcher" — the UI this phase adds).

## Global Constraints

- **Verified against the real installed libraries (2026-09-11,
  `httpx==0.28.1`), not remembered API shape:**
  - `httpx.Request(method, url, headers=..., extensions={"sni_hostname": hostname})`
    sent via `httpx.Client().send(req)` genuinely connects to `url`'s host
    while using `hostname` for the `Host` header behavior you pass
    explicitly and for TLS SNI/certificate-hostname verification when
    `url`'s host is a bare IP — confirmed with a real HTTPS request to
    `example.com` pinned to its resolved IP, both IPv4 and IPv6.
  - `httpx.URL(url).copy_with(host=ip)` correctly rewrites just the host,
    preserving scheme/port/path/query, and auto-brackets an IPv6 literal
    (`https://[2606:...]/path`) — confirmed directly.
  - `ipaddress.ip_address(x).is_global` is a drop-in replacement for the
    old `is_private or is_loopback or is_link_local or is_reserved`
    check — confirmed identical on every representative address
    (loopback, RFC1918, link-local, `240.0.0.0/4` reserved, real public
    IPv4/IPv6) **except** CGNAT (`100.64.0.0/10`, RFC 6598), which the old
    check missed and `is_global` correctly rejects.
  - `respx` mocks match on the outgoing request's actual URL — since
    requests now target the pinned IP-literal URL, every existing
    respx-mocked test's mock URL must be updated from the hostname-based
    URL to the pinned IP (`93.184.216.34`, the address the existing tests'
    `socket.getaddrinfo` monkeypatch already fakes) — confirmed this
    match still works correctly with the extra `Host`/`extensions` on the
    request.
- This phase still does **not** attempt SPEC.md §7.3's fuller Phase-2
  sandboxed-proxy mitigation (that's for real request *execution*, a
  different, larger surface with its own task). This phase closes the two
  specific gaps the final reviewer named in the schema-*fetch* surface
  only.
- No frontend component-level test infra exists in this codebase
  (`WorkspaceForm.tsx` and `DetailPanel.tsx` both have zero direct tests —
  only the pure `nodeLabel.ts` helper is tested). The new `WorkspaceList`
  component follows that same precedent — no new test dependency.

---

### Task 1: SSRF DNS-pinning + CGNAT fix (backend)

**Files:**
- Modify: `backend/app/schema/openapi.py` (full rewrite of the top half —
  fetch/safety section; `_resolve_refs`, `_first_2xx_response_schema`,
  `parse_openapi` are unchanged, keep them exactly as they are)
- Modify: `backend/app/schema/graphql.py` (`fetch_introspection` simplified
  to use the new shared `send_pinned`; `parse_graphql` and everything
  below it unchanged)
- Modify: `backend/tests/test_openapi_schema.py` (2 respx mock URLs
  updated, 2 new tests)
- Modify: `backend/tests/test_graphql_schema.py` (3 respx mock URLs
  updated, 3 new tests)
- Modify: `backend/tests/test_workspace_routes.py` (3 respx mock URLs
  updated, no new tests)

**Interfaces:**
- Produces (for graphql.py and any future caller): `send_pinned(method: str, url: str, error_cls: type[Exception], **kwargs: Any) -> httpx.Response` in `app.schema.openapi` — builds a DNS-pinned request, sends it, manually follows at most one redirect hop (itself re-pinned and re-validated), and raises `error_cls(...)` (the caller's own `*FetchError` type) on an unsafe/unresolvable target at either hop or a network failure. `**kwargs` forwards to `httpx.Request` (e.g. `json=...` for a POST body).
- Retires: `is_safe_url` (was Phase 1b Task 1's public rename of `_is_safe_url`) is deleted — its one job, a boolean pre-check, is now subsumed by `send_pinned`'s pinning path itself, so keeping a second, now-uncalled gate around would be dead code, not a safety net.

- [ ] **Step 1: Verify the two library behaviors yourself before writing code**

Run this from `backend/` to confirm `extensions={"sni_hostname": ...}` and
`copy_with(host=...)` behave as this plan's Global Constraints state,
against the real installed `httpx`:

```bash
.venv/bin/python -c "
import httpx, socket, ipaddress
hostname = 'example.com'
ip = socket.getaddrinfo(hostname, 443)[0][4][0]
pinned = httpx.URL(f'https://{hostname}/').copy_with(host=ip)
print('pinned url:', pinned)
req = httpx.Request('GET', pinned, headers={'Host': hostname}, extensions={'sni_hostname': hostname})
with httpx.Client(timeout=10.0) as client:
    resp = client.send(req, follow_redirects=False)
    print('status:', resp.status_code)
"
```

Expected: prints a pinned URL (IPv4 or IPv6, either is fine) and
`status: 200`. If this doesn't work exactly as shown, STOP and report —
the rest of this task depends on it.

- [ ] **Step 2: Rewrite `app/schema/openapi.py`'s fetch/safety section**

Replace everything in the file from the top through the end of
`fetch_spec` (i.e. everything before `_resolve_refs`) with:

```python
"""Real OpenAPI 3.x ingestion: fetch a real spec, validate it, flatten
its operations into node data with every `$ref` resolved inline.

Real fetched specs (tests/fixtures/petstore-openapi.json, the standard
Swagger Petstore example) use `$ref` for essentially every schema -- a
node's declared_request_schema/declared_response_schema would be useless
to any consumer without also holding the whole document, so this resolves
every local `#/...` pointer before a node is ever built. Local pointers
only: no external file/URL refs (SPEC.md's own no-live-resolution
discipline extends here)."""

from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

import httpx
from openapi_spec_validator import validate

_HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


class OpenAPIFetchError(Exception):
    pass


class OpenAPIValidationError(Exception):
    pass


def _resolve_safe_ip(hostname: str) -> str | None:
    """Resolves hostname and returns the first candidate IP to pin the
    real connection to, or None if resolution fails or ANY resolved
    address is not globally routable -- a hostname that round-robins
    between a safe and an unsafe address must not pass on a lucky first
    answer. `is_global` (verified 2026-09-11 against the real
    `ipaddress` stdlib module) correctly subsumes the old
    is_private/is_loopback/is_link_local/is_reserved checks AND
    additionally rejects CGNAT (100.64.0.0/10, RFC 6598) -- a real gap
    the old checks missed, since CGNAT is real internal space at several
    cloud providers."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return None
    ips = [info[4][0] for info in infos]
    if any(not ipaddress.ip_address(ip).is_global for ip in ips):
        return None
    return ips[0]


def _build_pinned_request(method: str, url: str, **kwargs: Any) -> httpx.Request | None:
    """Resolves and validates url's hostname via _resolve_safe_ip, then
    builds a real httpx.Request that connects directly to the validated
    IP -- closing the DNS-rebinding TOCTOU window between our own safety
    check and whatever httpx's own independent connection-time
    resolution would otherwise do. The original hostname is preserved as
    the Host header and the TLS SNI/certificate-hostname
    (extensions={"sni_hostname": ...}, verified against the real
    installed httpx 0.28.1, 2026-09-11) so the request is
    indistinguishable from an ordinary one to the target server. Returns
    None if the URL isn't http(s), has no hostname (e.g. a relative
    redirect Location -- rejected the same way the old is_safe_url
    rejected it), or the hostname doesn't resolve to an all-safe address
    set."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None
    hostname = parsed.hostname
    if not hostname:
        return None
    ip = _resolve_safe_ip(hostname)
    if ip is None:
        return None
    pinned_url = httpx.URL(url).copy_with(host=ip)
    headers = {**(kwargs.pop("headers", None) or {}), "Host": hostname}
    return httpx.Request(method, pinned_url, headers=headers, extensions={"sni_hostname": hostname}, **kwargs)


def send_pinned(method: str, url: str, error_cls: type[Exception], **kwargs: Any) -> httpx.Response:
    """Builds a pinned request (_build_pinned_request) and sends it,
    manually following at most one redirect hop -- the hop itself
    re-built and re-validated the same way, so an initially-safe URL
    that redirects to an internal address is still caught. Shared by
    fetch_spec (below) and fetch_introspection (app/schema/graphql.py)
    so both modules' fetch surfaces get identical SSRF-pinning behavior,
    not two independently-drifting copies. Raises error_cls (each
    module's own *FetchError) on an unsafe/unresolvable target or a
    network failure at either hop."""
    req = _build_pinned_request(method, url, **kwargs)
    if req is None:
        raise error_cls(f"{url} is not a permitted target")
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.send(req, follow_redirects=False)
    except httpx.HTTPError as exc:
        raise error_cls(f"could not reach {url}: {exc}") from exc
    if resp.is_redirect:
        location = resp.headers.get("location")
        redirect_req = _build_pinned_request(method, location, **kwargs) if location else None
        if redirect_req is None:
            raise error_cls(f"{url} redirected to a target that is not permitted")
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.send(redirect_req, follow_redirects=False)
        except httpx.HTTPError as exc:
            raise error_cls(f"could not reach {location}: {exc}") from exc
    return resp


def fetch_spec(source: str) -> dict[str, Any]:
    """`source` is a URL. Raises OpenAPIFetchError on any network
    failure, an unsafe/unresolvable target (at either the original URL
    or a redirect hop), a non-200 response, or an unparseable body (JSON
    or YAML, real specs are published as either)."""
    resp = send_pinned("GET", source, OpenAPIFetchError)
    if resp.status_code != 200:
        raise OpenAPIFetchError(f"{source} returned HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError:
        pass
    try:
        import yaml

        return yaml.safe_load(resp.text)
    except Exception as exc:  # noqa: BLE001 -- any YAML parse failure is a fetch-shaped failure here
        raise OpenAPIFetchError(f"{source} is neither valid JSON nor YAML") from exc
```

Everything from `_resolve_refs` onward in the current file is unchanged —
do not touch it.

- [ ] **Step 3: Simplify `app/schema/graphql.py`'s `fetch_introspection`**

Change the imports at the top of the file from:

```python
from app.schema.openapi import is_safe_url
```

to:

```python
from app.schema.openapi import send_pinned
```

Replace the whole `fetch_introspection` function with:

```python
def fetch_introspection(source: str) -> dict[str, Any]:
    """`source` is a GraphQL endpoint URL. POSTs the standard
    introspection query and returns its `data` payload -- the same shape
    `parse_graphql` accepts directly. Reuses openapi.py's `send_pinned`
    (same DNS-pinning + SSRF-baseline reasoning, SPEC.md §7.3, applied to
    this new fetch surface) rather than a second, independently-drifting
    copy."""
    resp = send_pinned("POST", source, GraphQLFetchError, json={"query": get_introspection_query()})
    if resp.status_code != 200:
        raise GraphQLFetchError(f"{source} returned HTTP {resp.status_code}")
    try:
        payload = resp.json()
    except ValueError as exc:
        raise GraphQLFetchError(f"{source} did not return valid JSON") from exc
    if not isinstance(payload, dict):
        raise GraphQLFetchError(f"{source} did not return a JSON object")
    if payload.get("errors"):
        raise GraphQLFetchError(f"{source} returned GraphQL errors: {payload['errors']}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise GraphQLFetchError(f"{source} returned no introspection data")
    return data
```

Also remove the now-unused `import httpx` line from this file if nothing
else in it uses `httpx` directly (check: `parse_graphql` and
`_describe_type` don't — only `fetch_introspection` used it, and it no
longer does).

`parse_graphql`, `_describe_type`, `_ROOT_TYPES`, `GraphQLFetchError`,
`GraphQLValidationError` are all unchanged — do not touch them.

- [ ] **Step 4: Update the 3 stale prose comments naming `is_safe_url`**

`is_safe_url` no longer exists (Step 2 deleted it). Fix these 3 comments,
which currently read (or close to):
`# for our own pre-fetch safety check (app/schema/openapi.py's is_safe_url).`

- `backend/tests/test_graphql_schema.py` (~line 86)
- `backend/tests/test_workspace_routes.py` (~line 19)
- `backend/tests/test_openapi_schema.py` (~line 67)

Change each to:
`# for our own pre-fetch safety check (app/schema/openapi.py's send_pinned).`

- [ ] **Step 5: Update existing respx-mocked tests' mock URLs**

Every existing test that mocks a fetch via `respx.get(...)` or
`respx.post(...)` on a hostname-based URL (`https://example.invalid/...`)
must change its mock to match the pinned IP-literal URL instead — real
outbound requests now target `https://93.184.216.34/<same path>`
(the fixed fake IP these tests' `socket.getaddrinfo` monkeypatch already
returns), not the original hostname.

In `backend/tests/test_openapi_schema.py`:
- `test_fetch_spec_real_http_get`: change
  `respx.get("https://example.invalid/openapi.json")` to
  `respx.get("https://93.184.216.34/openapi.json")`.
- `test_fetch_spec_network_failure_raises`: same URL change.

In `backend/tests/test_graphql_schema.py`:
- `test_fetch_introspection_real_http_post`: change
  `respx.post("https://example.invalid/graphql")` to
  `respx.post("https://93.184.216.34/graphql")`.
- `test_fetch_introspection_graphql_errors_raise`: same URL change.
- `test_fetch_introspection_rejects_a_non_object_json_response`: same URL
  change.

In `backend/tests/test_workspace_routes.py`:
- `test_create_workspace_from_a_real_url`: change
  `respx.get("https://example.invalid/openapi.json")` to
  `respx.get("https://93.184.216.34/openapi.json")`.
- `test_create_workspace_url_fetch_failure_is_502`: change
  `respx.get("https://example.invalid/down.json")` to
  `respx.get("https://93.184.216.34/down.json")`.
- `test_create_workspace_from_a_real_graphql_url`: change
  `respx.post("https://example.invalid/graphql")` to
  `respx.post("https://93.184.216.34/graphql")`.

Every other test in these three files is unchanged (including
`test_fetch_spec_rejects_a_private_ip_target` and
`test_fetch_introspection_rejects_a_private_ip_target`, which don't use
respx and don't need any change).

- [ ] **Step 6: Add 2 new tests to `test_openapi_schema.py`**

```python
@respx.mock
def test_fetch_spec_follows_one_safe_redirect_hop(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.get("https://93.184.216.34/old.json").mock(
        return_value=httpx.Response(302, headers={"location": "https://example.invalid/openapi.json"})
    )
    respx.get("https://93.184.216.34/openapi.json").mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    spec = fetch_spec("https://example.invalid/old.json")
    assert spec["info"]["title"] == FIXTURE["info"]["title"]


@respx.mock
def test_fetch_spec_rejects_a_redirect_to_an_unsafe_target(monkeypatch):
    # Deliberately NOT the blanket lambda every other test in this file
    # uses -- that fakes every hostname as safe, which would defeat this
    # specific test's point. Only "example.invalid" (unresolvable in
    # reality) is faked; a literal IP like 127.0.0.1 needs no DNS at all,
    # so it resolves for real and is correctly identified as loopback.
    real_getaddrinfo = socket.getaddrinfo

    def fake_getaddrinfo(host, *args, **kwargs):
        if host == "example.invalid":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    respx.get("https://93.184.216.34/redirect-to-internal.json").mock(
        return_value=httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})
    )
    with pytest.raises(OpenAPIFetchError):
        fetch_spec("https://example.invalid/redirect-to-internal.json")
```

- [ ] **Step 7: Add 3 new tests to `test_graphql_schema.py`**

```python
@respx.mock
def test_fetch_introspection_follows_one_safe_redirect_hop(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.post("https://93.184.216.34/old-graphql").mock(
        return_value=httpx.Response(302, headers={"location": "https://example.invalid/graphql"})
    )
    respx.post("https://93.184.216.34/graphql").mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    data = fetch_introspection("https://example.invalid/old-graphql")
    assert data == FIXTURE["data"]


@respx.mock
def test_fetch_introspection_rejects_a_redirect_to_an_unsafe_target(monkeypatch):
    real_getaddrinfo = socket.getaddrinfo

    def fake_getaddrinfo(host, *args, **kwargs):
        if host == "example.invalid":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    respx.post("https://93.184.216.34/redirect-to-internal").mock(
        return_value=httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})
    )
    with pytest.raises(GraphQLFetchError):
        fetch_introspection("https://example.invalid/redirect-to-internal")


@respx.mock
def test_fetch_introspection_network_failure_raises(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.post("https://93.184.216.34/graphql").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(GraphQLFetchError):
        fetch_introspection("https://example.invalid/graphql")
```

- [ ] **Step 8: Run the tests**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 38 passed (33 prior + 2 new in test_openapi_schema.py + 3 new
in test_graphql_schema.py).

- [ ] **Step 9: Commit**

```bash
git add backend/app/schema/openapi.py backend/app/schema/graphql.py \
        backend/tests/test_openapi_schema.py backend/tests/test_graphql_schema.py \
        backend/tests/test_workspace_routes.py
git commit -m "fix: DNS-pin schema-fetch requests, close CGNAT gap in SSRF guard"
```

---

### Task 2: Workspace list/picker UI (frontend)

**Files:**
- Create: `frontend/src/components/WorkspaceList.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: `listWorkspaces(): Promise<WorkspaceSummary[]>` and
  `getWorkspace(id: string): Promise<Workspace>` (both already exist,
  unchanged, in `frontend/src/api.ts`).
- Produces: `<WorkspaceList onLoad={(id: string) => void} refreshKey={number} currentId={string | null} />`
  — renders nothing (`null`) when there are no persisted workspaces yet;
  otherwise a `<select>` of `name (schema_kind)` options that calls
  `onLoad(id)` when one is picked. Re-fetches the list whenever
  `refreshKey` changes (bumped by `App.tsx` after a successful create, so
  a brand-new workspace appears without a page reload).

- [ ] **Step 1: Create `WorkspaceList.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { listWorkspaces, type WorkspaceSummary } from '../api'

/** The real "reopen a workspace you already built" affordance -- named
 * and deferred as a gap since Phase 1a, closed here. Lists this user's
 * persisted workspaces and loads whichever one is picked. Re-fetches
 * whenever `refreshKey` changes (App.tsx bumps it after a successful
 * create) so a brand-new workspace shows up without a page reload. */
export function WorkspaceList({ onLoad, refreshKey, currentId }: {
  onLoad: (id: string) => void
  refreshKey: number
  currentId: string | null
}) {
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([])

  useEffect(() => {
    listWorkspaces().then(setWorkspaces).catch(() => setWorkspaces([]))
  }, [refreshKey])

  if (workspaces.length === 0) return null

  return (
    <select
      className="workspace-list"
      value={currentId ?? ''}
      onChange={(e) => { if (e.target.value) onLoad(e.target.value) }}
      aria-label="Load existing workspace"
    >
      <option value="" disabled>Load existing…</option>
      {workspaces.map((w) => (
        <option key={w.id} value={w.id}>{w.name} ({w.schema_kind})</option>
      ))}
    </select>
  )
}
```

- [ ] **Step 2: Wire it into `App.tsx`**

Add a new import:

```typescript
import { WorkspaceList } from './components/WorkspaceList'
```

Add a new piece of state alongside the existing ones:

```typescript
  const [refreshKey, setRefreshKey] = useState(0)
```

Change `handleCreate`'s success branch from:

```typescript
      .then((ws) => { setWorkspace(ws); setStatuses({}) })
```

to:

```typescript
      .then((ws) => { setWorkspace(ws); setStatuses({}); setRefreshKey((k) => k + 1) })
```

Add a new handler, next to `handleCreate`:

```typescript
  function handleLoad(id: string) {
    setBusy(true)
    setError(null)
    getWorkspace(id)
      .then((ws) => { setWorkspace(ws); setStatuses({}) })
      .catch((e) => setError(String(e)))
      .finally(() => setBusy(false))
  }
```

In the JSX, inside `.hud-top`, add `<WorkspaceList .../>` right after the
`.brand` div and before `<WorkspaceForm .../>`:

```tsx
        <div className="hud-top">
          <div className="brand">parity<span>.</span></div>
          <WorkspaceList onLoad={handleLoad} refreshKey={refreshKey} currentId={workspace?.id ?? null} />
          <WorkspaceForm onCreate={handleCreate} busy={busy} />
        </div>
```

- [ ] **Step 3: Style the new `<select>`**

In `frontend/src/styles.css`, right after the `.brand span{...}` rule, add:

```css
.workspace-list{background:rgba(255,255,255,.04);border:1px solid var(--hair);
  color:var(--paper);font-family:var(--mono);font-size:11px;padding:9px 12px;
  border-radius:2px;margin-left:16px}
```

- [ ] **Step 4: Run the checks**

Run: `cd frontend && npx vitest run`
Expected: 7 passed (unchanged — no new test files this task, matching
the existing codebase's precedent of no direct tests for stateful/
effectful components like `WorkspaceForm.tsx`).

Run: `cd frontend && npx tsc -b`
Expected: no errors.

Run: `cd frontend && npx vite build`
Expected: succeeds (expected chunk-size warning only).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/WorkspaceList.tsx frontend/src/App.tsx frontend/src/styles.css
git commit -m "feat: workspace list/picker UI (closes Phase 1a's named gap)"
```

---

### Task 3: Live verification + `HANDOFF.md`

**Files:**
- Modify: `HANDOFF.md`

**Interfaces:**
- Consumes: Tasks 1-2's complete, committed changes. No new interfaces —
  this task verifies and documents.

- [ ] **Step 1: Start the real stack**

```bash
cd backend
docker compose up -d
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/alembic upgrade head
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/uvicorn app.main:app --port 8123 &
cd ../frontend && npm run dev &
```

- [ ] **Step 2: Live-verify in a real browser**

Open the app (`http://localhost:5173`).
- Create a workspace with a real OpenAPI URL
  (`https://petstore3.swagger.io/api/v3/openapi.json`) — confirm it still
  fetches and parses correctly (proving the DNS-pinning rewrite didn't
  break real external fetches, only tightened what it accepts).
- Create a second workspace with a real GraphQL URL
  (`https://countries.trevorblades.com/graphql`) — same confirmation for
  the GraphQL path.
- Confirm the new "Load existing…" picker now shows both workspaces by
  name and kind. Pick the first one — confirm the graph reloads to show
  it (proving the picker's `onLoad` → `getWorkspace` round-trip works for
  real, not just against mocked tests).
- Reload the page (full browser refresh) and confirm the picker still
  shows both workspaces (proving they're really in Postgres, not
  component state).

- [ ] **Step 3: Update `HANDOFF.md`**

Append a new `## Phase 1c: SSRF Hardening + Workspace List` section
(after the existing Phase 1b section), following that section's own
structure. It must state plainly:
- The DNS-pinning fix: `fetch_spec`/`fetch_introspection` now connect
  directly to the IP they validated, closing the specific DNS-rebinding
  TOCTOU window Phase 1b's final review flagged as a parked Minor.
- The CGNAT fix: the SSRF guard now correctly rejects
  `100.64.0.0/10` (RFC 6598), which the old `is_private`/`is_loopback`/
  `is_link_local`/`is_reserved` check missed.
- This still isn't SPEC.md §7.3's fuller Phase-2 sandboxed-proxy
  mitigation — that's for real request *execution* against arbitrary
  user-supplied target APIs, a different, larger surface. State this
  plainly so nobody reads this phase as having finished §7.3.
- The workspace-list/picker UI: closes the gap named in Phase 1a's
  HANDOFF and carried through Phase 1b's.
- The real test counts: confirm the actual final numbers from Task 1's
  Step 8 (`pytest -q`, expected 38) and Task 2's Step 4 (`vitest run`,
  expected 7) rather than trusting these — copy the real output.
- Next: Phase 2 (SPEC.md §10-11) — real request execution against both
  REST and GraphQL targets, the full SSRF-hardened proxy, and real
  drift-checking (response vs. declared schema).

- [ ] **Step 4: Commit**

```bash
git add HANDOFF.md
git commit -m "docs: Phase 1c HANDOFF — SSRF pinning + workspace list, live-verified"
```
