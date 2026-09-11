# Phase 2a: Real Request Execution + REST Drift-Checking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the honest `501` on `POST /api/workspaces/{id}/requests`
with the real thing: a real SSRF-guarded outbound proxy, a real curl
parser, real REST request→node matching, and real REST drift-checking
(response vs. declared JSON Schema) — the actual product value SPEC.md
§2 describes. GraphQL request-matching + drift-checking and the
frontend's real request-builder UI are Phase 2b's job (SPEC.md's own
Phase 2 covers both REST and GraphQL together; this plan splits it the
same way Phase 1 was split into 1a/1b/1c, so each half stays
independently testable and reviewable).

**Architecture:** The SSRF guard built in Phase 1c for schema-fetching
moves into its own module (`app/proxy/ssrf_guard.py`, matching SPEC.md
§9's folder structure) and gains real cross-host credential-stripping on
redirect — Phase 1c's final review named this as a trap for "a future
caller that [passes credentials]"; this plan is that caller. A small
hand-rolled curl parser (verified against `uncurl` and found genuinely
inadequate — see Task 2) turns a pasted curl command into a structured
request. `POST /api/workspaces/{id}/requests` fires it through the guard,
matches the real request to a REST `Node` by method + path-template
(literal segments beating a templated one at the same position — verified
against a real ambiguity in the Petstore fixture), validates the real
response against that node's declared JSON Schema, and persists
`Request`/`Response`/`DriftFinding` rows with sensitive headers redacted.

**Tech Stack:** `jsonschema` (already a transitive dependency of
`openapi-spec-validator`, made an explicit direct dependency here since
this plan calls it directly), `httpx` (already a dependency). No new
external dependency for curl parsing — see Task 2's verified reasoning
for why `uncurl` was tried and rejected.

**Spec:** [`SPEC.md`](../../../SPEC.md) §6 (the full data flow this plan
implements, steps 4-8), §7.3 (SSRF), §7.5 (the `request`/`response`/
`drift_finding` tables), §7.6 (the exact endpoint shapes), §9 (folder
structure), §11 (testing discipline — the adversarial SSRF test and the
"real curl commands, not hand-typed" requirement), §13 (the curl-parser
and REST-matching decisions this plan makes for real, against real data).

## Global Constraints

- **`POST /api/workspaces/{id}/requests`'s real body shape is
  `{method, url, headers, body}` — no `node_id`** (SPEC.md §7.6, verified
  against the current placeholder route: it never actually validated a
  `node_id` shape, so this is a clean replacement, not a breaking change
  to a real contract). The backend matches the fired request to a node
  itself, after the fact (SPEC.md §6 step 6) — the frontend never tells
  it which node it "meant."
- **Verified against the real installed libraries/data before this plan
  was written (2026-09-11), not remembered behavior:**
  - `uncurl==0.0.11` was installed and tested against real devtools-shaped
    curl commands. It genuinely conflates `-b`/`--data-binary` with real
    curl's `-b`/`--cookie` (confirmed via its own source: `-b` is
    `argparse`-mapped to `--data-binary`, never to cookies), and has no
    `-G` support at all. Both are flags SPEC.md §7.1 explicitly names as
    needed. **Decision: hand-roll the parser** (Task 2), per SPEC.md
    §13's own stated fallback. `uncurl` is NOT a dependency of this plan.
  - The real Petstore fixture (`tests/fixtures/petstore-openapi.json`)
    has a genuine literal-vs-template ambiguity: `/pet/findByStatus`,
    `/pet/findByTags`, and `/pet/{petId}` are all real 2-segment `GET`
    paths under `/pet`. The REST-matching algorithm (Task 5) was
    verified against this real data: literal segments must beat a
    templated one at the same position, or `/pet/findByStatus` would
    incorrectly match `/pet/{petId}`.
  - The real Petstore fixture's `servers[0].url` is `/api/v3` — a real,
    non-empty base path. A real request's full path (e.g.
    `/api/v3/pet/123`) will NOT segment-count-match a node's
    `path_template` (`/pet/{petId}`) unless that base path is stripped
    first. `Workspace.base_path` (Task 3) and its use in matching
    (Task 5) exist because of this real, verified necessity — not
    speculative future-proofing.
  - `jsonschema.validate()`'s `ValidationError` carries a real, usable
    `.json_path` (e.g. `"$.id"`) and `.message` (e.g. `"'x' is not of
    type 'integer'"") — used directly for `drift_finding.detail`.
- **GraphQL workspaces are honestly `unverified_no_match` in this plan**,
  not guessed at. `POST /api/workspaces/{id}/requests` fires the real
  request for ANY workspace (the proxy itself is protocol-agnostic), but
  only attempts REST matching+drift when `workspace.schema_kind ==
  "openapi"`. Phase 2b adds the GraphQL side.
- **Live verification for this plan is backend-level** (a running
  backend + real HTTP calls, e.g. via a script or `curl` against the
  live server), not through the browser UI — the real request-builder
  frontend panel (SPEC.md §8.4) is Phase 2b's job. Confirm this
  explicitly in the final task's HANDOFF entry so it isn't read as a
  skipped step.

---

### Task 1: Relocate + harden the SSRF guard (`app/proxy/ssrf_guard.py`)

**Files:**
- Create: `backend/app/proxy/__init__.py` (empty)
- Create: `backend/app/proxy/ssrf_guard.py`
- Modify: `backend/app/schema/openapi.py` (remove `_resolve_safe_ip`,
  `_build_pinned_request`, `send_pinned`; import `send_pinned` from the
  new module instead)
- Modify: `backend/app/schema/graphql.py` (same import change)
- Create: `backend/tests/test_ssrf_guard.py` (moves the NAT64 test from
  `test_openapi_schema.py` here, adds the adversarial tests SPEC.md §11
  requires, adds the new redirect-credential-stripping tests)
- Modify: `backend/tests/test_openapi_schema.py` (remove the NAT64 test —
  it now lives in `test_ssrf_guard.py`)

**Interfaces:**
- Produces (for every later task in this plan, and for `schema/openapi.py`/
  `schema/graphql.py`, unchanged from their Phase 1c callers' point of
  view): `send_pinned(method: str, url: str, error_cls: type[Exception], *, timeout: float = 15.0, **kwargs: Any) -> httpx.Response`
  in `app.proxy.ssrf_guard` — identical behavior to Phase 1c's version,
  PLUS: on a redirect hop whose target hostname differs from the
  original, strips `Authorization`, `Cookie`, and `Proxy-Authorization`
  (case-insensitive) from any `headers` kwarg before re-sending. A
  same-host redirect keeps every header unchanged.

- [ ] **Step 1: Create the new module**

`backend/app/proxy/__init__.py`: empty file.

`backend/app/proxy/ssrf_guard.py`:

```python
"""The real SSRF baseline guard (SPEC.md §7.3): DNS-resolve a target,
reject it if unsafe, and connect directly to the validated IP rather than
letting the HTTP client independently re-resolve at connect time (closing
the DNS-rebinding TOCTOU window Phase 1c's final review named). Shared by
every outbound fetch in this backend -- the two schema-fetch functions
(app/schema/openapi.py, app/schema/graphql.py) and the real
request-execution proxy (app/proxy/client.py, this plan's Task 4) -- so
there is exactly one copy of this security-critical logic. Moved here
from app/schema/openapi.py (Phase 1c's final review, finding M10: SPEC.md
§9 names this module explicitly; it lived in schema/openapi.py only
because no other caller existed yet)."""

from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

_SENSITIVE_HEADERS = {"authorization", "cookie", "proxy-authorization"}


def _resolve_safe_ip(hostname: str) -> str | None:
    """Resolves hostname and returns the first candidate IP to pin the
    real connection to, or None if resolution fails or ANY resolved
    address is unsafe -- a hostname that round-robins between a safe and
    an unsafe address must not pass on a lucky first answer. Rejects: not
    globally routable (subsumes private/loopback/link-local/reserved/
    CGNAT), multicast, a 6to4 address (2002::/16), and the NAT64
    well-known prefix 64:ff9b::/96 (maps to an internal IPv4 address on
    any NAT64 network -- exactly what an IPv6-only cloud subnet often
    is). Verified against the real ipaddress module, Phase 1c."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return None
    ips = [info[4][0] for info in infos]
    nat64 = ipaddress.ip_network("64:ff9b::/96")
    for raw in ips:
        addr = ipaddress.ip_address(raw)
        if not addr.is_global or addr.is_multicast or getattr(addr, "sixtofour", None) is not None or addr in nat64:
            return None
    return ips[0]


def _build_pinned_request(method: str, url: str, **kwargs: Any) -> httpx.Request | None:
    """Resolves and validates url's hostname via _resolve_safe_ip, then
    builds a real httpx.Request that connects directly to the validated
    IP -- closing the DNS-rebinding TOCTOU window between our own safety
    check and whatever httpx's own independent connection-time
    resolution would otherwise do. The original hostname/port is
    preserved as the Host header and the TLS SNI/certificate-hostname
    (extensions={"sni_hostname": ...}) so the request is indistinguishable
    from an ordinary one to the target server. Returns None if the URL
    isn't http(s), has no hostname (e.g. a relative redirect Location --
    rejected the same way a URL with no resolvable target always is), or
    the hostname doesn't resolve to an all-safe address set."""
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
    headers = {**(kwargs.pop("headers", None) or {}), "Host": httpx.URL(url).netloc.decode("ascii")}
    return httpx.Request(method, pinned_url, headers=headers, extensions={"sni_hostname": hostname}, **kwargs)


def send_pinned(method: str, url: str, error_cls: type[Exception], *, timeout: float = 15.0, **kwargs: Any) -> httpx.Response:
    """Builds a pinned request (_build_pinned_request) and sends it,
    manually following at most one redirect hop -- the hop itself
    re-built and re-validated the same way, so an initially-safe URL that
    redirects to an internal address is still caught. Raises error_cls
    (each caller's own error type) on an unsafe/unresolvable target or a
    network failure at either hop.

    On a redirect whose target hostname differs from the original,
    strips Authorization/Cookie/Proxy-Authorization from any `headers`
    kwarg before re-sending -- the real fix for a trap Phase 1c's final
    review named and explicitly deferred (this function had no
    credential-carrying caller then; app/proxy/client.py, added in this
    plan, is the first one). A same-host redirect keeps every header
    unchanged, since a same-origin redirect has no reason to drop them."""
    try:
        req = _build_pinned_request(method, url, **kwargs)
        if req is None:
            raise error_cls(f"{url} is not a permitted target")
        with httpx.Client(timeout=timeout) as client:
            resp = client.send(req, follow_redirects=False)
    except error_cls:
        raise
    except Exception as exc:  # noqa: BLE001 -- _build_pinned_request can raise httpx.InvalidURL
        # (not an httpx.HTTPError subclass) on a malformed URL, and the
        # actual send can raise httpx.HTTPError on a network failure --
        # both are fetch-shaped failures from this function's caller's
        # point of view, so both become a clean error_cls instead of an
        # uncaught 500.
        raise error_cls(f"could not reach {url}: {exc}") from exc

    if resp.is_redirect:
        location = resp.headers.get("location")
        redirect_kwargs = dict(kwargs)
        if location:
            original_host = urlparse(url).hostname
            redirect_host = urlparse(location).hostname
            if redirect_host and redirect_host != original_host:
                headers = dict(redirect_kwargs.get("headers") or {})
                for key in list(headers):
                    if key.lower() in _SENSITIVE_HEADERS:
                        del headers[key]
                redirect_kwargs["headers"] = headers
        try:
            redirect_req = _build_pinned_request(method, location, **redirect_kwargs) if location else None
            if redirect_req is None:
                raise error_cls(f"{url} redirected to a target that is not permitted")
            with httpx.Client(timeout=timeout) as client:
                resp = client.send(redirect_req, follow_redirects=False)
        except error_cls:
            raise
        except Exception as exc:  # noqa: BLE001 -- same reasoning as above
            raise error_cls(f"could not reach {location}: {exc}") from exc
    return resp
```

- [ ] **Step 2: Update `app/schema/openapi.py`**

Remove `_resolve_safe_ip`, `_build_pinned_request`, and `send_pinned`
entirely from this file (they now live in `app/proxy/ssrf_guard.py`).
Remove the now-unused `import ipaddress` and `import socket` lines if
nothing else in the file uses them (check: `_resolve_refs`,
`_first_2xx_response_schema`, `parse_openapi`, `fetch_spec` don't use
`ipaddress`/`socket` directly). Keep `from urllib.parse import urlparse`
(still used by `fetch_spec`... actually check: does anything in the
REMAINING code use `urlparse` directly? If not, remove that import too).

Add this import at the top, alongside the other imports:

```python
from app.proxy.ssrf_guard import send_pinned
```

`fetch_spec` itself is unchanged (it already just calls `send_pinned(...)`
— only the import source moves).

- [ ] **Step 3: Update `app/schema/graphql.py`**

Change:

```python
from app.schema.openapi import send_pinned
```

to:

```python
from app.proxy.ssrf_guard import send_pinned
```

`fetch_introspection` itself is unchanged.

- [ ] **Step 4: Move the NAT64 test, add the SSRF adversarial suite**

In `backend/tests/test_openapi_schema.py`, remove
`test_resolve_safe_ip_rejects_nat64_and_sixtofour_addresses` entirely (it
moves below).

Create `backend/tests/test_ssrf_guard.py`:

```python
"""The adversarial pass SPEC.md §11 requires once Phase 2's real
request-firing exists: prove the SSRF boundary actually holds, not just
that it's present. Also covers the redirect-credential-stripping
behavior added in this plan (Task 1)."""

import socket

import httpx
import pytest
import respx

from app.proxy.ssrf_guard import _resolve_safe_ip, send_pinned


class _FetchError(Exception):
    pass


def test_resolve_safe_ip_rejects_nat64_and_sixtofour_addresses():
    assert _resolve_safe_ip("64:ff9b::a00:1") is None  # NAT64, maps to 10.0.0.1
    assert _resolve_safe_ip("2002:7f00:1::") is None    # 6to4, maps to 127.0.0.1


def test_send_pinned_rejects_loopback():
    with pytest.raises(_FetchError):
        send_pinned("GET", "http://127.0.0.1/secret", _FetchError)


def test_send_pinned_rejects_the_cloud_metadata_endpoint():
    with pytest.raises(_FetchError):
        send_pinned("GET", "http://169.254.169.254/latest/meta-data/", _FetchError)


def test_send_pinned_rejects_an_rfc1918_private_address():
    with pytest.raises(_FetchError):
        send_pinned("GET", "http://10.0.0.5/internal", _FetchError)


def test_send_pinned_rejects_explicit_localhost_by_hostname():
    with pytest.raises(_FetchError):
        send_pinned("GET", "http://localhost/", _FetchError)


@respx.mock
def test_send_pinned_strips_credentials_on_a_cross_host_redirect(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.get("https://93.184.216.34/old").mock(
        return_value=httpx.Response(302, headers={"location": "https://other.invalid/new"})
    )
    respx.get("https://93.184.216.34/new").mock(return_value=httpx.Response(200))
    send_pinned("GET", "https://example.invalid/old", _FetchError, headers={"Authorization": "Bearer secret"})
    sent_headers = respx.calls.last.request.headers
    assert "authorization" not in sent_headers


@respx.mock
def test_send_pinned_preserves_credentials_on_a_same_host_redirect(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.get("https://93.184.216.34/old").mock(
        return_value=httpx.Response(302, headers={"location": "https://example.invalid/new"})
    )
    respx.get("https://93.184.216.34/new").mock(return_value=httpx.Response(200))
    send_pinned("GET", "https://example.invalid/old", _FetchError, headers={"Authorization": "Bearer secret"})
    sent_headers = respx.calls.last.request.headers
    assert sent_headers.get("authorization") == "Bearer secret"
```

- [ ] **Step 5: Run the tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_ssrf_guard.py -v`
Expected: all 7 pass.

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 38 passed (39 minus the 1 NAT64 test moved, plus the 7 in the
new file — 39 - 1 + 7 = 45; confirm the real number from the actual
output rather than trusting this arithmetic, and report it exactly).

- [ ] **Step 6: Commit**

```bash
git add backend/app/proxy/__init__.py backend/app/proxy/ssrf_guard.py \
        backend/app/schema/openapi.py backend/app/schema/graphql.py \
        backend/tests/test_ssrf_guard.py backend/tests/test_openapi_schema.py
git commit -m "refactor: move SSRF guard to app/proxy/ssrf_guard.py, strip credentials on cross-host redirect"
```

---

### Task 2: The curl parser (`app/proxy/curl_parser.py`)

**Files:**
- Create: `backend/app/proxy/curl_parser.py`
- Test: `backend/tests/test_curl_parser.py`

**Interfaces:**
- Produces: `class CurlParseError(Exception)`; `parse_curl(curl_command: str) -> dict[str, Any]` returning `{"method": str, "url": str, "headers": dict[str, str], "body": str | None}`.

- [ ] **Step 1: Write `app/proxy/curl_parser.py`**

```python
"""Real curl-command parsing: a small hand-rolled parser over
shlex.split, covering exactly the flag set SPEC.md §7.1 names as needed
(-X/--request, -H/--header, -d/--data/--data-raw, -u/--user, -G,
-b/--cookie). `uncurl` (the existing library SPEC.md §7.1 said to try
first) was evaluated directly against real devtools-shaped curl commands
and found to genuinely conflate `-b` with `--data-binary` (real curl's
`-b` is `--cookie`; confirmed via uncurl's own argparse source: `-b` is
never mapped to cookies) and to have no `-G` support at all -- both flags
this project explicitly needs. Not used; this hand-rolled parser is the
real SPEC.md §13 decision, made against real data."""

from __future__ import annotations

import base64
import shlex
from typing import Any


class CurlParseError(Exception):
    pass


def parse_curl(curl_command: str) -> dict[str, Any]:
    """Returns {"method": str, "url": str, "headers": dict[str, str],
    "body": str | None}. Anything outside the supported flag set is
    ignored, not rejected -- a real devtools-exported curl command
    carries many flags (--compressed, -s, --location) this tool has no
    use for, and the real content this portfolio's own testing
    discipline (SPEC.md §11) cares about is the ones it DOES support,
    verified against real devtools-shaped input."""
    try:
        tokens = shlex.split(curl_command)
    except ValueError as exc:
        raise CurlParseError(f"could not tokenize curl command: {exc}") from exc
    if not tokens or tokens[0] != "curl":
        raise CurlParseError("input must start with 'curl'")

    method: str | None = None
    url: str | None = None
    headers: dict[str, str] = {}
    data_parts: list[str] = []
    cookie_parts: list[str] = []
    user: str | None = None
    use_get_with_query = False

    i = 1
    while i < len(tokens):
        tok = tokens[i]
        if tok in ("-X", "--request"):
            i += 1
            method = tokens[i] if i < len(tokens) else None
        elif tok in ("-H", "--header"):
            i += 1
            if i < len(tokens):
                key, _, value = tokens[i].partition(":")
                headers[key.strip()] = value.strip()
        elif tok in ("-d", "--data", "--data-raw", "--data-binary"):
            i += 1
            if i < len(tokens):
                data_parts.append(tokens[i])
        elif tok in ("-u", "--user"):
            i += 1
            user = tokens[i] if i < len(tokens) else None
        elif tok == "-G":
            use_get_with_query = True
        elif tok in ("-b", "--cookie"):
            i += 1
            if i < len(tokens):
                cookie_parts.append(tokens[i])
        elif not tok.startswith("-") and url is None:
            url = tok
        i += 1

    if url is None:
        raise CurlParseError("no URL found in curl command")

    body = "&".join(data_parts) if data_parts else None
    if use_get_with_query and body:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{body}"
        body = None
        method = method or "GET"
    method = (method or ("POST" if body else "GET")).upper()

    if cookie_parts:
        headers.setdefault("Cookie", "; ".join(cookie_parts))
    if user and "Authorization" not in headers:
        headers["Authorization"] = "Basic " + base64.b64encode(user.encode()).decode()

    return {"method": method, "url": url, "headers": headers, "body": body}
```

- [ ] **Step 2: Write `tests/test_curl_parser.py`**

```python
import pytest

from app.proxy.curl_parser import CurlParseError, parse_curl

# Shaped exactly like a real Chrome DevTools "Copy as cURL (bash)" export
# for a POST with a bearer token and a JSON body (SPEC.md §11: tested
# against a real devtools shape, not a hand-typed minimal example).
DEVTOOLS_POST = """curl 'https://api.example.com/v1/pets' \\
  -H 'authority: api.example.com' \\
  -H 'accept: application/json' \\
  -H 'authorization: Bearer abc123' \\
  -H 'content-type: application/json' \\
  -H 'user-agent: Mozilla/5.0' \\
  --data-raw '{"name":"Fido","tag":"dog"}' """


def test_parses_a_real_devtools_post_with_bearer_token_and_json_body():
    result = parse_curl(DEVTOOLS_POST)
    assert result["method"] == "POST"
    assert result["url"] == "https://api.example.com/v1/pets"
    assert result["headers"]["authorization"] == "Bearer abc123"
    assert result["headers"]["content-type"] == "application/json"
    assert result["body"] == '{"name":"Fido","tag":"dog"}'


def test_parses_a_get_with_query_params_and_no_explicit_method():
    result = parse_curl("curl 'https://api.example.com/v1/pets?limit=10&tag=dog' -H 'accept: application/json'")
    assert result["method"] == "GET"
    assert result["url"] == "https://api.example.com/v1/pets?limit=10&tag=dog"


def test_parses_explicit_put_with_cookie_and_data():
    result = parse_curl("curl -X PUT 'https://api.example.com/v1/pets/1' -b 'session=xyz' -d 'name=Rex'")
    assert result["method"] == "PUT"
    assert result["headers"]["Cookie"] == "session=xyz"
    assert result["body"] == "name=Rex"


def test_parses_basic_auth_into_an_authorization_header():
    result = parse_curl("curl -u user:pass 'https://api.example.com/v1/secure'")
    assert result["headers"]["Authorization"] == "Basic dXNlcjpwYXNz"


def test_parses_g_flag_as_query_params_not_a_body():
    result = parse_curl("curl -G 'https://api.example.com/v1/search' -d 'q=fido' -d 'limit=5'")
    assert result["method"] == "GET"
    assert result["url"] == "https://api.example.com/v1/search?q=fido&limit=5"
    assert result["body"] is None


def test_rejects_input_that_does_not_start_with_curl():
    with pytest.raises(CurlParseError):
        parse_curl("not a curl command")


def test_rejects_a_command_with_no_url():
    with pytest.raises(CurlParseError):
        parse_curl("curl -X GET")
```

- [ ] **Step 3: Run the tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_curl_parser.py -v`
Expected: all 7 pass.

- [ ] **Step 4: Commit**

```bash
git add backend/app/proxy/curl_parser.py backend/tests/test_curl_parser.py
git commit -m "feat: hand-rolled curl parser (uncurl evaluated and rejected, see module docstring)"
```

---

### Task 3: Models — `Request`, `Response`, `DriftFinding`, `Workspace.base_path`

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/schema/openapi.py` (add `extract_base_path`)
- Modify: `backend/app/routes/workspaces.py` (populate + expose `base_path`)
- Modify: `backend/tests/test_workspace_routes.py` (assert `base_path` is
  present and correct for a real OpenAPI workspace)
- Create: `backend/alembic/versions/<autogenerated>.py` (via `alembic
  revision --autogenerate`, Step 4 below)

**Interfaces:**
- Produces: `Request`, `Response`, `DriftFinding` SQLAlchemy models
  (SPEC.md §7.5, exact columns below); `Workspace.base_path: str`;
  `extract_base_path(spec: dict) -> str` in `app.schema.openapi`.

- [ ] **Step 1: Add the new columns and models to `app/models.py`**

Add `base_path` to the existing `Workspace` class, right after
`schema_source`:

```python
    base_path: Mapped[str] = mapped_column(Text, default="")  # OpenAPI servers[0].url's path component (e.g. "/api/v3"); "" for GraphQL or a spec with no servers entry
```

Add three new classes at the end of the file, after `Node`:

```python
class Request(Base):
    __tablename__ = "request"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"))
    node_id: Mapped[str | None] = mapped_column(ForeignKey("node.id"), nullable=True)
    method: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(Text)
    headers: Mapped[dict] = mapped_column(JSONB)  # redacted before persisting, see app/redact.py
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Response(Base):
    __tablename__ = "response"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    request_id: Mapped[str] = mapped_column(ForeignKey("request.id"))
    status_code: Mapped[int] = mapped_column(Integer)
    headers: Mapped[dict] = mapped_column(JSONB)  # redacted before persisting
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DriftFinding(Base):
    __tablename__ = "drift_finding"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    response_id: Mapped[str] = mapped_column(ForeignKey("response.id"))
    node_id: Mapped[str | None] = mapped_column(ForeignKey("node.id"), nullable=True)
    status: Mapped[str] = mapped_column(String)  # "matched" | "violated" | "unverified_no_schema" | "unverified_no_match"
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
```

- [ ] **Step 2: Add `extract_base_path` to `app/schema/openapi.py`**

Add this function, right after `fetch_spec` (before `_resolve_refs`):

```python
def extract_base_path(spec: dict[str, Any]) -> str:
    """Returns the path component of the spec's first `servers` entry
    (e.g. "/api/v3"), or "" if there's no servers entry or its url has no
    path component. A real request's full path must have this prefix
    stripped before matching against a Node's path_template, which is
    stored relative to this base -- verified necessary against the real
    Petstore fixture, whose own servers[0].url is "/api/v3" (SPEC.md
    §7.2/§13)."""
    servers = spec.get("servers") or []
    if not servers:
        return ""
    url = servers[0].get("url", "")
    return urlparse(url).path.rstrip("/")
```

(`urlparse` is already imported at the top of this file.)

- [ ] **Step 3: Populate + expose `base_path` in `app/routes/workspaces.py`**

Add `extract_base_path` to the existing import line:

```python
from app.schema.openapi import OpenAPIFetchError, OpenAPIValidationError, extract_base_path, fetch_spec, parse_openapi
```

In `create_workspace`, change:

```python
    if schema_kind == "openapi":
```

to:

```python
    base_path = ""
    if schema_kind == "openapi":
```

Then, inside that same `if schema_kind == "openapi":` branch, change:

```python
        try:
            parsed_nodes = parse_openapi(spec)
        except OpenAPIValidationError as exc:
            raise HTTPException(status_code=422, detail=f"invalid OpenAPI spec: {exc}") from exc
    else:
```

to:

```python
        try:
            parsed_nodes = parse_openapi(spec)
        except OpenAPIValidationError as exc:
            raise HTTPException(status_code=422, detail=f"invalid OpenAPI spec: {exc}") from exc
        base_path = extract_base_path(spec)
    else:
```

(The `graphql` branch below this is untouched — `base_path` stays `""`
for it, from the initialization above.)

Finally, change the `Workspace(...)` constructor call:

```python
    workspace = Workspace(
        user_id=DEFAULT_USER_ID, name=name, schema_kind=schema_kind,
        schema_source=url or "pasted", raw_schema=spec,
    )
```

to:

```python
    workspace = Workspace(
        user_id=DEFAULT_USER_ID, name=name, schema_kind=schema_kind,
        schema_source=url or "pasted", raw_schema=spec, base_path=base_path,
    )
```

In `get_workspace`, change the return statement from:

```python
    return {
        "id": workspace.id, "name": workspace.name, "schema_kind": workspace.schema_kind,
        "nodes": node_dicts,
        "edges": [{"from_node": a, "to_node": b} for a, b in edges],
    }
```

to:

```python
    return {
        "id": workspace.id, "name": workspace.name, "schema_kind": workspace.schema_kind,
        "base_path": workspace.base_path,
        "nodes": node_dicts,
        "edges": [{"from_node": a, "to_node": b} for a, b in edges],
    }
```

- [ ] **Step 4: Generate and apply the migration**

```bash
cd backend
docker compose up -d
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/alembic revision --autogenerate -m "add request, response, drift_finding tables and workspace.base_path"
```

Read the generated migration file. `Workspace.base_path`'s `default=""`
in the model is a Python-side default (applied when the ORM constructs a
new row) — it is NOT reflected in the DDL, so autogenerate will almost
certainly produce something like `sa.Column('base_path', sa.Text(),
nullable=False)` with no default at the database level. Applied as-is,
this would fail against any `workspace` table that already has rows
(Postgres can't add a `NOT NULL` column with no default to a non-empty
table). Fix the generated migration by hand: add `server_default=""` to
that `op.add_column(...)` call, so it works whether the table is empty or
not:

```python
sa.Column('base_path', sa.Text(), nullable=False, server_default=""),
```

Also confirm the generated migration creates `request`, `response`,
`drift_finding` tables matching the models exactly (all timestamp
columns `timezone=True`, matching this project's established convention
from Phase 1a's own migration fix) — autogenerate should get this right
automatically since `DateTime(timezone=True)` IS reflected in DDL, but
verify it in the generated file rather than assuming.

Apply it:

```bash
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/alembic upgrade head
```

Expected: no errors, and `alembic current` shows the new revision as head.

- [ ] **Step 5: Update `tests/test_workspace_routes.py`**

In `test_list_and_get_real_workspace`, add an assertion after the
existing ones:

```python
    assert got["base_path"] == "/api/v3"  # the real Petstore fixture's servers[0].url
```

- [ ] **Step 6: Run the tests**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all pass (report the real count).

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/app/schema/openapi.py backend/app/routes/workspaces.py \
        backend/tests/test_workspace_routes.py backend/alembic/versions/
git commit -m "feat: Request/Response/DriftFinding models, Workspace.base_path"
```

---

### Task 4: The real proxy (`app/proxy/client.py`) + header redaction

**Files:**
- Create: `backend/app/proxy/client.py`
- Create: `backend/app/redact.py`
- Test: `backend/tests/test_proxy_client.py`
- Test: `backend/tests/test_redact.py`

**Interfaces:**
- Consumes: `send_pinned` from Task 1's `app.proxy.ssrf_guard`.
- Produces: `class ProxyError(Exception)`; `fire_request(method: str, url: str, headers: dict[str, str] | None, body: str | None) -> tuple[httpx.Response, int]` (response, latency in milliseconds) in `app.proxy.client`. `redact_headers(headers: dict[str, str]) -> dict[str, str]` in `app.redact`.

- [ ] **Step 1: Write `app/redact.py`**

```python
"""Redacts sensitive header values before persisting a Request/Response
to Postgres (SPEC.md §7.5: "redacted before persisting, same discipline
as loom's carabiner/lockstep subprocess redaction"). The real value is
still used for the live request/response -- only the stored copy is
scrubbed."""

from __future__ import annotations

_SENSITIVE_HEADER_NAMES = {"authorization", "cookie", "set-cookie", "proxy-authorization", "x-api-key"}


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        key: ("[REDACTED]" if key.lower() in _SENSITIVE_HEADER_NAMES else value)
        for key, value in headers.items()
    }
```

- [ ] **Step 2: Write `tests/test_redact.py`**

```python
from app.redact import redact_headers


def test_redacts_known_sensitive_headers_case_insensitively():
    result = redact_headers({"Authorization": "Bearer secret", "AUTHORIZATION": "x", "content-type": "application/json"})
    assert result["Authorization"] == "[REDACTED]"
    assert result["AUTHORIZATION"] == "[REDACTED]"
    assert result["content-type"] == "application/json"


def test_redacts_cookie_and_api_key_headers():
    result = redact_headers({"Cookie": "session=abc", "X-Api-Key": "k1", "Set-Cookie": "a=b"})
    assert result["Cookie"] == "[REDACTED]"
    assert result["X-Api-Key"] == "[REDACTED]"
    assert result["Set-Cookie"] == "[REDACTED]"


def test_leaves_unrelated_headers_untouched():
    result = redact_headers({"Accept": "application/json", "User-Agent": "test"})
    assert result == {"Accept": "application/json", "User-Agent": "test"}
```

- [ ] **Step 3: Write `app/proxy/client.py`**

```python
"""The real outbound request-execution proxy (SPEC.md §6 step 5, §7.3):
fires a real HTTP request to a real target, through the same SSRF-pinned
guard every other outbound fetch in this backend uses."""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.proxy.ssrf_guard import send_pinned


class ProxyError(Exception):
    pass


def fire_request(method: str, url: str, headers: dict[str, str] | None, body: str | None) -> tuple[httpx.Response, int]:
    """Returns (response, latency_ms). Raises ProxyError on an
    unsafe/unresolvable target or a network failure (via send_pinned's
    own error handling)."""
    kwargs: dict[str, Any] = {}
    if headers:
        kwargs["headers"] = headers
    if body is not None:
        kwargs["content"] = body.encode("utf-8")
    start = time.monotonic()
    resp = send_pinned(method, url, ProxyError, **kwargs)
    latency_ms = int((time.monotonic() - start) * 1000)
    return resp, latency_ms
```

- [ ] **Step 4: Write `tests/test_proxy_client.py`**

```python
import socket

import httpx
import pytest
import respx

from app.proxy.client import ProxyError, fire_request


@respx.mock
def test_fire_request_returns_a_real_response_and_latency(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.get("https://93.184.216.34/pets/1").mock(return_value=httpx.Response(200, json={"id": 1, "name": "Fido"}))
    resp, latency_ms = fire_request("GET", "https://example.invalid/pets/1", None, None)
    assert resp.status_code == 200
    assert resp.json() == {"id": 1, "name": "Fido"}
    assert latency_ms >= 0


@respx.mock
def test_fire_request_sends_real_headers_and_body(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.post("https://93.184.216.34/pets").mock(return_value=httpx.Response(201))
    fire_request("POST", "https://example.invalid/pets", {"Content-Type": "application/json"}, '{"name":"Rex"}')
    sent = respx.calls.last.request
    assert sent.headers["content-type"] == "application/json"
    assert sent.content == b'{"name":"Rex"}'


def test_fire_request_rejects_an_unsafe_target():
    with pytest.raises(ProxyError):
        fire_request("GET", "http://127.0.0.1/secret", None, None)
```

- [ ] **Step 5: Run the tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_redact.py tests/test_proxy_client.py -v`
Expected: all 6 pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/proxy/client.py backend/app/redact.py \
        backend/tests/test_proxy_client.py backend/tests/test_redact.py
git commit -m "feat: real outbound request proxy + header redaction before persisting"
```

---

### Task 5: REST matching (`app/matching.py`) + REST drift (`app/drift/rest.py`)

**Files:**
- Create: `backend/app/matching.py`
- Create: `backend/app/drift/__init__.py` (empty)
- Create: `backend/app/drift/rest.py`
- Test: `backend/tests/test_matching.py`
- Test: `backend/tests/test_drift_rest.py`

**Interfaces:**
- Produces: `match_rest_node(nodes: list[dict], method: str, url: str, base_path: str) -> dict | None` in `app.matching` (each `nodes` entry needs at least `id`, `method`, `path_template` keys). `check_rest_drift(declared_response_schema: dict | None, response_body_text: str | None) -> tuple[str, str | None]` in `app.drift.rest`.

- [ ] **Step 1: Write `app/matching.py`**

```python
"""Matches a real fired request to the REST Node it corresponds to
(SPEC.md §6 step 6): method + path-template match, literal segments
beating a templated one at the same position -- verified against a real
ambiguity in the Petstore fixture (/pet/findByStatus, /pet/findByTags,
and /pet/{petId} are all real 2-segment GET paths under /pet; a naive
segment-count match alone would let /pet/{petId} wrongly claim a request
meant for /pet/findByStatus)."""

from __future__ import annotations

from urllib.parse import urlparse


def match_rest_node(nodes: list[dict], method: str, url: str, base_path: str) -> dict | None:
    """`nodes` are REST node dicts carrying at least `id`, `method`,
    `path_template`. `base_path` (Workspace.base_path) is stripped from
    the request's path before matching -- a real spec's declared paths
    are relative to its servers[0].url, not to the request's full path.
    Returns the best-matching node dict, or None if no node's template
    has the same segment count and (literal-or-template) shape as the
    request path."""
    path = urlparse(url).path
    if base_path and path.startswith(base_path):
        path = path[len(base_path):]
    path_segs = [s for s in path.strip("/").split("/") if s]

    best: dict | None = None
    best_score = -1
    for node in nodes:
        if node.get("method") is None or node["method"].upper() != method.upper():
            continue
        tmpl = node.get("path_template")
        if tmpl is None:
            continue
        tmpl_segs = [s for s in tmpl.strip("/").split("/") if s]
        if len(tmpl_segs) != len(path_segs):
            continue
        score = 0
        ok = True
        for tmpl_seg, path_seg in zip(tmpl_segs, path_segs):
            if tmpl_seg.startswith("{") and tmpl_seg.endswith("}"):
                continue
            if tmpl_seg == path_seg:
                score += 1
            else:
                ok = False
                break
        if ok and score > best_score:
            best = node
            best_score = score
    return best
```

- [ ] **Step 2: Write `tests/test_matching.py`**

```python
from app.matching import match_rest_node

NODES = [
    {"id": "findByStatus", "method": "GET", "path_template": "/pet/findByStatus"},
    {"id": "findByTags", "method": "GET", "path_template": "/pet/findByTags"},
    {"id": "getPetById", "method": "GET", "path_template": "/pet/{petId}"},
    {"id": "addPet", "method": "POST", "path_template": "/pet"},
]


def test_literal_segment_beats_a_template_at_the_same_position():
    result = match_rest_node(NODES, "GET", "https://api.example.com/api/v3/pet/findByStatus", "/api/v3")
    assert result["id"] == "findByStatus"


def test_a_real_id_matches_the_template_node():
    result = match_rest_node(NODES, "GET", "https://api.example.com/api/v3/pet/123", "/api/v3")
    assert result["id"] == "getPetById"


def test_matches_by_method_too_not_only_path():
    result = match_rest_node(NODES, "POST", "https://api.example.com/api/v3/pet", "/api/v3")
    assert result["id"] == "addPet"


def test_no_match_on_segment_count_mismatch():
    assert match_rest_node(NODES, "GET", "https://api.example.com/api/v3/pet/1/extra", "/api/v3") is None


def test_no_match_when_no_node_has_that_method():
    assert match_rest_node(NODES, "DELETE", "https://api.example.com/api/v3/pet/1", "/api/v3") is None


def test_empty_base_path_still_matches_a_request_with_no_prefix():
    nodes = [{"id": "root", "method": "GET", "path_template": "/pets"}]
    result = match_rest_node(nodes, "GET", "https://api.example.com/pets", "")
    assert result["id"] == "root"
```

- [ ] **Step 3: Write `app/drift/rest.py`**

`backend/app/drift/__init__.py`: empty file.

`backend/app/drift/rest.py`:

```python
"""Validates a real response against a REST node's declared response
schema (SPEC.md §6 step 7, §7.5's drift_finding.status enum): a real
jsonschema check against real JSON Schema (openapi.py's $ref-resolved
output), not a hand-rolled shape comparison."""

from __future__ import annotations

import json
from typing import Any

import jsonschema


def check_rest_drift(declared_response_schema: dict[str, Any] | None, response_body_text: str | None) -> tuple[str, str | None]:
    """Returns (status, detail). status is one of "matched", "violated",
    or "unverified_no_schema" (no declared schema exists to check
    against -- the node has no schema information for the response it
    actually got, so there's nothing to compare). Returning
    "unverified_no_match" is the caller's job, for when no node matched
    at all -- this function is only ever called once a node IS known."""
    if declared_response_schema is None:
        return "unverified_no_schema", None
    try:
        body: Any = json.loads(response_body_text) if response_body_text else None
    except ValueError:
        return "violated", "response body is not valid JSON"
    try:
        jsonschema.validate(body, declared_response_schema)
    except jsonschema.ValidationError as exc:
        return "violated", f"{exc.json_path}: {exc.message}"
    return "matched", None
```

- [ ] **Step 4: Write `tests/test_drift_rest.py`**

```python
from app.drift.rest import check_rest_drift

SCHEMA = {
    "type": "object",
    "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
    "required": ["id", "name"],
}


def test_no_declared_schema_is_unverified_no_schema():
    status, detail = check_rest_drift(None, '{"id": 1, "name": "Fido"}')
    assert status == "unverified_no_schema"
    assert detail is None


def test_matching_response_is_matched():
    status, detail = check_rest_drift(SCHEMA, '{"id": 1, "name": "Fido"}')
    assert status == "matched"
    assert detail is None


def test_wrong_type_is_violated_with_a_real_diff():
    status, detail = check_rest_drift(SCHEMA, '{"id": "not-an-int", "name": "Fido"}')
    assert status == "violated"
    assert "id" in detail
    assert "integer" in detail


def test_missing_required_field_is_violated():
    status, detail = check_rest_drift(SCHEMA, '{"id": 1}')
    assert status == "violated"
    assert "name" in detail


def test_non_json_body_is_violated():
    status, detail = check_rest_drift(SCHEMA, "not json at all")
    assert status == "violated"
    assert "not valid JSON" in detail
```

- [ ] **Step 5: Run the tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_matching.py tests/test_drift_rest.py -v`
Expected: all 11 pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/matching.py backend/app/drift/ \
        backend/tests/test_matching.py backend/tests/test_drift_rest.py
git commit -m "feat: real REST request-matching and jsonschema-based drift validation"
```

---

### Task 6: The real routes

**Files:**
- Modify: `backend/app/routes/requests.py` (full rewrite)
- Create: `backend/app/routes/curl_parse.py`
- Modify: `backend/app/main.py` (register the new router)
- Modify: `backend/tests/test_request_routes.py` (full rewrite — the
  honest-501 tests are replaced with real-behavior tests)
- Create: `backend/tests/test_curl_parse_route.py`

**Interfaces:**
- Consumes: Task 2's `parse_curl`/`CurlParseError`, Task 4's
  `fire_request`/`ProxyError`/`redact_headers`, Task 5's
  `match_rest_node`/`check_rest_drift`.
- Produces: the real `POST /api/curl-parse`, `POST
  /api/workspaces/{id}/requests`, `GET /api/workspaces/{id}/requests`,
  `GET /api/workspaces/{id}/nodes/{node_id}/history` routes, matching
  SPEC.md §7.6 exactly.

- [ ] **Step 1: Write `app/routes/curl_parse.py`**

```python
"""POST /api/curl-parse -- no side effects, just parses (SPEC.md §7.6)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.proxy.curl_parser import CurlParseError, parse_curl

router = APIRouter(prefix="/api", tags=["curl"])


@router.post("/curl-parse")
def curl_parse_route(body: dict) -> dict:
    curl = body.get("curl")
    if not isinstance(curl, str) or not curl.strip():
        raise HTTPException(status_code=422, detail="curl is required")
    try:
        return parse_curl(curl)
    except CurlParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
```

- [ ] **Step 2: Rewrite `app/routes/requests.py`**

```python
"""Real request execution (SPEC.md §6 steps 4-8, §7.6): fires a real
request through the SSRF-guarded proxy, matches it to a known REST Node
(GraphQL matching arrives in Phase 2b -- until then a GraphQL workspace's
requests are honestly unverified_no_match, never guessed), validates the
real response against that node's declared schema, and persists
Request/Response/DriftFinding with headers redacted before storage.
Replaces Phase 0/1's honest 501 entirely."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.drift.rest import check_rest_drift
from app.matching import match_rest_node
from app.models import DriftFinding, Node, Request, Response, Workspace
from app.proxy.client import ProxyError, fire_request
from app.redact import redact_headers

router = APIRouter(prefix="/api/workspaces", tags=["requests"])


def _safe_json(text: str | None) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text


@router.post("/{workspace_id}/requests", status_code=201)
def send_request(workspace_id: str, body: dict, session: Session = Depends(get_session)) -> dict:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="unknown workspace id")

    method = body.get("method")
    url = body.get("url")
    headers = body.get("headers") or {}
    req_body = body.get("body")
    if not method or not url:
        raise HTTPException(status_code=422, detail="method and url are required")

    try:
        resp, latency_ms = fire_request(method, url, headers, req_body)
    except ProxyError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    node: Node | None = None
    if workspace.schema_kind == "openapi":
        node_dicts = [
            {"id": n.id, "method": n.method, "path_template": n.path_template}
            for n in workspace.nodes
        ]
        matched = match_rest_node(node_dicts, method, url, workspace.base_path)
        if matched:
            node = session.get(Node, matched["id"])

    request_row = Request(
        workspace_id=workspace.id, node_id=node.id if node else None,
        method=method.upper(), url=url, headers=redact_headers(headers), body=req_body,
    )
    session.add(request_row)
    session.flush()

    response_row = Response(
        request_id=request_row.id, status_code=resp.status_code,
        headers=redact_headers(dict(resp.headers)), body=resp.text, latency_ms=latency_ms,
    )
    session.add(response_row)
    session.flush()

    if node is not None:
        node.call_count += 1
        status, detail = check_rest_drift(node.declared_response_schema, resp.text)
    else:
        status, detail = "unverified_no_match", None

    drift_row = DriftFinding(response_id=response_row.id, node_id=node.id if node else None, status=status, detail=detail)
    session.add(drift_row)
    session.commit()

    return {
        "request": {"id": request_row.id, "node_id": request_row.node_id, "method": request_row.method, "url": request_row.url},
        "response": {"id": response_row.id, "status_code": response_row.status_code, "body": _safe_json(resp.text), "latency_ms": latency_ms},
        "drift_finding": {"id": drift_row.id, "status": drift_row.status, "detail": drift_row.detail},
    }


@router.get("/{workspace_id}/requests")
def list_requests(workspace_id: str, session: Session = Depends(get_session)) -> list[dict]:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="unknown workspace id")
    rows = (
        session.query(Request)
        .filter(Request.workspace_id == workspace_id)
        .order_by(Request.sent_at.desc())
        .all()
    )
    return [
        {"id": r.id, "node_id": r.node_id, "method": r.method, "url": r.url, "sent_at": r.sent_at.isoformat()}
        for r in rows
    ]


@router.get("/{workspace_id}/nodes/{node_id}/history")
def node_history(workspace_id: str, node_id: str, session: Session = Depends(get_session)) -> list[dict]:
    node = session.get(Node, node_id)
    if node is None or node.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="unknown node id")
    rows = (
        session.query(DriftFinding)
        .filter(DriftFinding.node_id == node_id)
        .order_by(DriftFinding.created_at.desc())
        .all()
    )
    return [
        {"id": f.id, "status": f.status, "detail": f.detail, "created_at": f.created_at.isoformat()}
        for f in rows
    ]
```

- [ ] **Step 3: Register the new router in `app/main.py`**

Add the import:

```python
from app.routes.curl_parse import router as curl_parse_router
```

Add the registration, alongside the existing two:

```python
app.include_router(curl_parse_router)
```

- [ ] **Step 4: Rewrite `tests/test_request_routes.py`**

```python
import json
import socket
from pathlib import Path

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "petstore-openapi.json").read_text())


def _fake_getaddrinfo(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )


@respx.mock
def test_send_a_real_request_that_matches_a_node_and_drifts(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Petstore", "schema_kind": "openapi", "raw_schema": FIXTURE,
    }).json()

    # Missing photoUrls would ALSO be flagged (it's a required field on
    # the real Pet schema) -- including it here isolates the assertion to
    # the one real defect this test is about: id's wrong type. Verified
    # against the real fixture's real Pet schema (2026-09-11): this exact
    # body produces exactly one real jsonschema error, at $.id.
    respx.get("https://93.184.216.34/api/v3/pet/1").mock(
        return_value=httpx.Response(200, json={"id": "not-an-int", "name": "Fido", "photoUrls": []})
    )
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "GET", "url": "https://example.invalid/api/v3/pet/1", "headers": {}, "body": None,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["request"]["node_id"] is not None
    assert body["response"]["status_code"] == 200
    assert body["drift_finding"]["status"] == "violated"
    assert "id" in body["drift_finding"]["detail"]


@respx.mock
def test_send_a_request_that_matches_no_node_is_unverified_no_match(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Petstore", "schema_kind": "openapi", "raw_schema": FIXTURE,
    }).json()

    respx.get("https://93.184.216.34/api/v3/totally/unknown").mock(return_value=httpx.Response(200))
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "GET", "url": "https://example.invalid/api/v3/totally/unknown", "headers": {}, "body": None,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["request"]["node_id"] is None
    assert body["drift_finding"]["status"] == "unverified_no_match"


def test_send_against_an_unsafe_target_is_502():
    ws = client.post("/api/workspaces", json={
        "name": "x", "schema_kind": "openapi",
        "raw_schema": {"openapi": "3.0.0", "info": {"title": "t", "version": "1"}, "paths": {}},
    }).json()
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "GET", "url": "http://127.0.0.1/secret", "headers": {}, "body": None,
    })
    assert r.status_code == 502


def test_send_against_unknown_workspace_is_404():
    r = client.post("/api/workspaces/00000000-0000-0000-0000-000000000099/requests", json={
        "method": "GET", "url": "https://example.invalid/x", "headers": {}, "body": None,
    })
    assert r.status_code == 404


def test_send_requires_method_and_url():
    ws = client.post("/api/workspaces", json={
        "name": "x", "schema_kind": "openapi",
        "raw_schema": {"openapi": "3.0.0", "info": {"title": "t", "version": "1"}, "paths": {}},
    }).json()
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={"headers": {}, "body": None})
    assert r.status_code == 422


@respx.mock
def test_request_history_lists_what_was_sent(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Petstore", "schema_kind": "openapi", "raw_schema": FIXTURE,
    }).json()
    respx.get("https://93.184.216.34/api/v3/pet/1").mock(return_value=httpx.Response(200, json={"id": 1, "name": "Fido"}))
    client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "GET", "url": "https://example.invalid/api/v3/pet/1", "headers": {}, "body": None,
    })
    history = client.get(f"/api/workspaces/{ws['id']}/requests").json()
    assert len(history) == 1
    assert history[0]["method"] == "GET"


@respx.mock
def test_node_history_lists_that_nodes_drift_findings(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Petstore", "schema_kind": "openapi", "raw_schema": FIXTURE,
    }).json()
    node_id = next(n["id"] for n in client.get(f"/api/workspaces/{ws['id']}").json()["nodes"] if n["operation_id"] == "getPetById")
    # photoUrls is required on the real Pet schema -- included here so
    # this response is genuinely, fully valid against it (verified
    # 2026-09-11), making "matched" the real, correct outcome, not an
    # assumption.
    respx.get("https://93.184.216.34/api/v3/pet/1").mock(return_value=httpx.Response(200, json={"id": 1, "name": "Fido", "photoUrls": []}))
    client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "GET", "url": "https://example.invalid/api/v3/pet/1", "headers": {}, "body": None,
    })
    history = client.get(f"/api/workspaces/{ws['id']}/nodes/{node_id}/history").json()
    assert len(history) == 1
    assert history[0]["status"] == "matched"


def test_node_history_for_unknown_node_is_404():
    ws = client.post("/api/workspaces", json={
        "name": "x", "schema_kind": "openapi",
        "raw_schema": {"openapi": "3.0.0", "info": {"title": "t", "version": "1"}, "paths": {}},
    }).json()
    r = client.get(f"/api/workspaces/{ws['id']}/nodes/00000000-0000-0000-0000-000000000099/history")
    assert r.status_code == 404
```

- [ ] **Step 5: Write `tests/test_curl_parse_route.py`**

```python
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_curl_parse_route_returns_a_structured_request():
    r = client.post("/api/curl-parse", json={"curl": "curl -X POST 'https://api.example.com/x' -d 'a=1'"})
    assert r.status_code == 200
    body = r.json()
    assert body["method"] == "POST"
    assert body["url"] == "https://api.example.com/x"
    assert body["body"] == "a=1"


def test_curl_parse_route_rejects_invalid_input():
    r = client.post("/api/curl-parse", json={"curl": "not a curl command"})
    assert r.status_code == 422


def test_curl_parse_route_requires_the_curl_field():
    r = client.post("/api/curl-parse", json={})
    assert r.status_code == 422
```

- [ ] **Step 6: Run the tests**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all pass — report the real total.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/requests.py backend/app/routes/curl_parse.py backend/app/main.py \
        backend/tests/test_request_routes.py backend/tests/test_curl_parse_route.py
git commit -m "feat: real request execution + curl-parse routes (SPEC.md §7.6)"
```

---

### Task 7: Live verification + `HANDOFF.md`

**Files:**
- Modify: `HANDOFF.md`

**Interfaces:**
- Consumes: Tasks 1-6's complete, committed changes. No new interfaces —
  this task verifies and documents.

- [ ] **Step 1: Start the real stack**

```bash
cd backend
docker compose up -d
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/alembic upgrade head
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/uvicorn app.main:app --port 8123 &
```

- [ ] **Step 2: Live-verify against a real public API**

This plan's live verification is backend-level (the real request-builder
frontend is Phase 2b's job — see this plan's Global Constraints). Run
real HTTP calls against the live server:

```bash
# 1. Create a real workspace against the real, live Petstore API
curl -s -X POST http://127.0.0.1:8123/api/workspaces \
  -H 'Content-Type: application/json' \
  -d '{"name": "Petstore live", "schema_kind": "openapi", "schema_source_url": "https://petstore3.swagger.io/api/v3/openapi.json"}'
# note the returned workspace "id"

# 2. Parse a real curl command via the new endpoint
curl -s -X POST http://127.0.0.1:8123/api/curl-parse \
  -H 'Content-Type: application/json' \
  -d '{"curl": "curl -X GET '"'"'https://petstore3.swagger.io/api/v3/pet/findByStatus?status=available'"'"'"}'

# 3. Fire a real request against the real live Petstore API (replace <id> with the workspace id from step 1)
curl -s -X POST http://127.0.0.1:8123/api/workspaces/<id>/requests \
  -H 'Content-Type: application/json' \
  -d '{"method": "GET", "url": "https://petstore3.swagger.io/api/v3/pet/findByStatus?status=available", "headers": {}, "body": null}'
# confirm: a real 200 response, a real node_id match (findByStatus), and
# a real drift_finding.status -- "matched" or "violated" depending on
# whether the live Petstore API's real response currently matches its
# own declared schema (either outcome is a legitimate, real result --
# report exactly what came back, don't force it to "matched")

# 4. Confirm history
curl -s http://127.0.0.1:8123/api/workspaces/<id>/requests
curl -s http://127.0.0.1:8123/api/workspaces/<id>/nodes/<node_id>/history
```

Also confirm the SSRF guard holds against the real live server (not just
in tests): `curl -s -X POST http://127.0.0.1:8123/api/workspaces/<id>/requests -d '{"method":"GET","url":"http://169.254.169.254/","headers":{},"body":null}' -H 'Content-Type: application/json'` must return `502`.

- [ ] **Step 3: Update `HANDOFF.md`**

Append a new `## Phase 2a: Real Request Execution + REST Drift-Checking`
section (after the Phase 1c section), following that section's own
structure. It must state plainly:
- The real SSRF-guarded proxy, curl parser (and the real, verified
  reason `uncurl` was rejected), REST request-matching (and the real
  Petstore ambiguity it was verified against), and REST drift-checking
  via real `jsonschema`.
- The real test counts (confirm the actual final number from Step 6 of
  Task 6's `pytest -q` output).
- The real live-verification results from Step 2 above — including
  whatever the live Petstore API's actual drift status came back as
  (state the real outcome, don't paraphrase it as always "matched").
- Explicitly state this is backend-level verification, not
  browser/frontend verification — the frontend still shows the Phase
  0/1 UI (a bare "Send" button with no way to specify method/url/
  headers/body), and clicking it will currently fail since it still
  calls the old `sendRequest(workspaceId, nodeId)` shape. This is a
  real, deliberate, temporary state — Phase 2b replaces the frontend's
  Send flow with a real request-builder panel that calls this plan's
  real endpoint shape.
- GraphQL workspaces: requests fire for real but are honestly
  `unverified_no_match` (Phase 2b adds GraphQL matching+drift).
- Next: Phase 2b (SPEC.md §10) — GraphQL request-matching + drift
  validation, and the frontend's real request-builder panel + curl-paste
  UI + history view (SPEC.md §8.4).

- [ ] **Step 4: Commit**

```bash
git add HANDOFF.md
git commit -m "docs: Phase 2a HANDOFF — real request execution, live-verified against Petstore"
```
