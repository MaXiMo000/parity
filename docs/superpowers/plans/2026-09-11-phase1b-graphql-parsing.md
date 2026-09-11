# Phase 1b: GraphQL Schema Parsing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real GraphQL schema ingestion (live introspection or a pasted
SDL document) as the second schema source, completing SPEC.md's Phase 1
scope alongside Phase 1a's OpenAPI ingestion — one `Node` row per field
reachable from `Query`/`Mutation`, persisted the same way OpenAPI operations
already are.

**Architecture:** A new `app/schema/graphql.py` module mirrors
`app/schema/openapi.py`'s shape exactly (`fetch_*` + `parse_*`, both raising
their own `*Error` types), reusing the same SSRF baseline guard. `POST
/api/workspaces` grows a `schema_kind == "graphql"` branch that calls it.
The frontend adds a kind selector to the existing workspace-creation form
and teaches `DetailPanel` to show a GraphQL field's real type/field name
instead of REST's method/path when that's what the node actually is.

**Tech Stack:** `graphql-core` (real reference GraphQL implementation in
Python — verified installed behavior below, not remembered API shape),
`httpx` (already a dependency), `respx` (already a dev dependency, same
mocking pattern Phase 1a's OpenAPI tests use).

**Spec:** [`SPEC.md`](../../../SPEC.md) — particularly §7.2 (the two schema
parsers, exactly what each produces), §7.3 (SSRF baseline), §7.5 (data
model — `node.type_name`/`node.field_name` already exist, added in Phase 1a
for exactly this).

## Global Constraints

- GraphQL v1 scope is `Query` and `Mutation` fields only — `Subscription` is
  a different, streaming transport shape, explicitly out of scope (SPEC.md
  §7.2).
- Reuse the existing SSRF baseline guard (`is_safe_url`, renamed from
  `openapi.py`'s private `_is_safe_url` in Task 1) rather than duplicating
  it — a second, drifted copy of a security-relevant check is the one thing
  this portfolio never allows.
- `graphql-core`'s real, verified exception shapes (2026-09-11, against
  `graphql-core==3.2.12`): `build_schema` raises `GraphQLSyntaxError` (a
  `GraphQLError` subclass) on malformed SDL; `build_client_schema` raises
  bare `TypeError` on a malformed introspection payload and bare `KeyError`
  on one missing required keys (e.g. no `"types"` list). These three share
  no common base except `Exception` itself — catch `Exception` broadly in
  `parse_graphql`, the same justified pattern `openapi.py`'s `parse_openapi`
  already uses for its own two-exception-types-no-common-base situation.
  Do not narrow this to a single guessed exception class.
- The real public GraphQL API used for the live fixture is
  `https://countries.trevorblades.com/graphql` (verified reachable
  2026-09-11, no auth required, 6 real `Query` fields, no `Mutation` type).
- No `.github/workflows/ci.yml` changes needed this phase — GraphQL fetching
  uses the same `httpx`-over-the-network shape Postgres/OpenAPI already
  exercises in CI; no new service dependency.
- No workspace-list/picker UI in this phase — that gap was explicitly named
  and deferred in Phase 1a's `HANDOFF.md` and stays deferred here. Do not
  fold it into this plan's tasks.

---

### Task 1: `app/schema/graphql.py` — the real GraphQL parser

**Files:**
- Modify: `backend/app/schema/openapi.py` (rename `_is_safe_url` → public
  `is_safe_url`, its two call sites, nothing else)
- Modify: `backend/pyproject.toml` (add `graphql-core>=3.2` to
  `dependencies`)
- Create: `backend/app/schema/graphql.py`
- Create: `backend/tests/fixtures/countries-graphql-introspection.json`
  (real, fetched — see Step 2)
- Test: `backend/tests/test_graphql_schema.py`

**Interfaces:**
- Consumes: `app.schema.openapi.is_safe_url(url: str) -> bool` (this task
  makes it public — it is currently `_is_safe_url` in that same file).
- Produces (for Task 2):
  - `class GraphQLFetchError(Exception)`
  - `class GraphQLValidationError(Exception)`
  - `fetch_introspection(source: str) -> dict[str, Any]` — POSTs the
    standard introspection query to `source`, returns the response's
    `"data"` payload directly (the exact shape `parse_graphql`'s dict
    branch accepts). Raises `GraphQLFetchError` on any network failure,
    non-200, non-JSON body, a `"errors"` key in the response, or a missing/
    non-dict `"data"` key.
  - `parse_graphql(schema_input: dict[str, Any] | str) -> list[dict[str, Any]]`
    — `str` is treated as a pasted SDL document; `dict` is treated as an
    introspection result's `"data"` payload (i.e. `fetch_introspection`'s
    return value, or the equivalent pasted-and-parsed-as-JSON value).
    Returns one node dict per `Query`/`Mutation` field, each with keys
    `kind` (always `"graphql_field"`), `method`, `path_template`,
    `operation_id` (all always `None` — those are REST-only), `type_name`
    (`"Query"` or `"Mutation"`), `field_name`, `declared_request_schema`
    (a dict of `{arg_name: type_descriptor}`, or `None` if the field takes
    no arguments), `declared_response_schema` (a type descriptor). Raises
    `GraphQLValidationError` if `schema_input` doesn't build into a real
    schema.
  - A type descriptor is `{"kind": "NAMED", "name": str, "nullable": bool}`
    or `{"kind": "LIST", "of": <type descriptor>, "nullable": bool}`.

- [ ] **Step 1: Rename the SSRF guard to public, add the new dependency**

In `backend/app/schema/openapi.py`, rename `_is_safe_url` to `is_safe_url`
(the function definition on line 33, and its two call sites on lines 62 and
70). No other change to that file.

In `backend/pyproject.toml`, add `"graphql-core>=3.2"` to the
`dependencies` list (alongside the existing `httpx`, `PyYAML`, etc.
entries).

Run: `cd backend && .venv/bin/pip install -e ".[dev]"`
Expected: installs `graphql-core` with no errors.

- [ ] **Step 2: Fetch the real fixture**

Run this exact command from `backend/` (uses the now-installed
`graphql-core` and the already-installed `httpx`):

```bash
.venv/bin/python -c "
import httpx, json
from graphql import get_introspection_query
q = get_introspection_query()
r = httpx.post('https://countries.trevorblades.com/graphql', json={'query': q}, timeout=15.0)
r.raise_for_status()
data = r.json()
assert 'errors' not in data, data
with open('tests/fixtures/countries-graphql-introspection.json', 'w') as f:
    json.dump(data, f, indent=2)
print('wrote', len(json.dumps(data)), 'bytes')
"
```

Expected: prints `wrote <N> bytes` and creates
`backend/tests/fixtures/countries-graphql-introspection.json`. This is a
real, live-fetched response from a real public GraphQL API (no auth,
verified reachable 2026-09-11) — the same "real fixture, not synthetic"
discipline `tests/fixtures/petstore-openapi.json` already follows.

- [ ] **Step 3: Write `app/schema/graphql.py`**

```python
"""Real GraphQL ingestion: live introspection over HTTP, or a pasted SDL
document, both producing the same flat node list Postgres persists. Mirrors
app/schema/openapi.py's shape (fetch/parse, one Node per operation) applied
to GraphQL's own shape: one Node per field reachable from Query/Mutation
(SPEC.md §7.2 — Subscription is a different, streaming transport shape,
out of scope for v1)."""

from __future__ import annotations

from typing import Any

import httpx
from graphql import (
    GraphQLList,
    GraphQLNonNull,
    build_client_schema,
    build_schema,
    get_introspection_query,
)

from app.schema.openapi import is_safe_url

_ROOT_TYPES = ("Query", "Mutation")


class GraphQLFetchError(Exception):
    pass


class GraphQLValidationError(Exception):
    pass


def fetch_introspection(source: str) -> dict[str, Any]:
    """`source` is a GraphQL endpoint URL. POSTs the standard introspection
    query and returns its `data` payload -- the same shape `parse_graphql`
    accepts directly. Reuses openapi.py's `is_safe_url` (same SSRF-baseline
    reasoning, SPEC.md §7.3, applied to this new fetch surface) and follows
    at most one redirect hop manually, re-checked, matching fetch_spec's
    own pattern."""
    if not is_safe_url(source):
        raise GraphQLFetchError(f"{source} is not a permitted target")
    body = {"query": get_introspection_query()}
    try:
        resp = httpx.post(source, json=body, timeout=15.0, follow_redirects=False)
    except httpx.HTTPError as exc:
        raise GraphQLFetchError(f"could not reach {source}: {exc}") from exc
    if resp.is_redirect:
        location = resp.headers.get("location")
        if not location or not is_safe_url(location):
            raise GraphQLFetchError(f"{source} redirected to a target that is not permitted")
        try:
            resp = httpx.post(location, json=body, timeout=15.0, follow_redirects=False)
        except httpx.HTTPError as exc:
            raise GraphQLFetchError(f"could not reach {location}: {exc}") from exc
    if resp.status_code != 200:
        raise GraphQLFetchError(f"{source} returned HTTP {resp.status_code}")
    try:
        payload = resp.json()
    except ValueError as exc:
        raise GraphQLFetchError(f"{source} did not return valid JSON") from exc
    if payload.get("errors"):
        raise GraphQLFetchError(f"{source} returned GraphQL errors: {payload['errors']}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise GraphQLFetchError(f"{source} returned no introspection data")
    return data


def _describe_type(t: Any) -> dict[str, Any]:
    """Flattens a graphql-core type object into a small JSON-safe shape:
    {"kind": "NAMED", "name": "...", "nullable": bool} or, for a list,
    {"kind": "LIST", "of": <nested>, "nullable": bool}. NonNull unwraps to
    its inner type with nullable=False -- verified against the real
    library (2026-09-11): GraphQLNonNull never wraps another GraphQLNonNull,
    so one unwrap per level is exact, not an approximation."""
    if isinstance(t, GraphQLNonNull):
        inner = _describe_type(t.of_type)
        inner["nullable"] = False
        return inner
    if isinstance(t, GraphQLList):
        return {"kind": "LIST", "of": _describe_type(t.of_type), "nullable": True}
    return {"kind": "NAMED", "name": t.name, "nullable": True}


def parse_graphql(schema_input: dict[str, Any] | str) -> list[dict[str, Any]]:
    """`schema_input` is either a pasted SDL document (str) or an
    introspection result's `data` payload (dict, e.g. fetch_introspection's
    return value). Returns a flat list of node dicts, one per field
    reachable from Query or Mutation (Subscription out of scope, SPEC.md
    §7.2). Raises GraphQLValidationError if the input doesn't build into a
    real schema."""
    try:
        schema = (
            build_schema(schema_input)
            if isinstance(schema_input, str)
            else build_client_schema(schema_input)
        )
    except Exception as exc:  # noqa: BLE001 -- verified against the real library (2026-09-11):
        # build_schema raises GraphQLSyntaxError on bad SDL; build_client_schema
        # raises TypeError on a malformed payload and KeyError on one missing
        # required keys (e.g. no "types" list) -- three types sharing no
        # common base except Exception itself (confirmed via their real
        # __mro__), so this catches all three deliberately rather than
        # guessing at one specific class or import path.
        raise GraphQLValidationError(f"not a valid GraphQL schema: {exc}") from exc

    nodes: list[dict[str, Any]] = []
    for type_name in _ROOT_TYPES:
        root_type = getattr(schema, f"{type_name.lower()}_type", None)
        if root_type is None:
            continue
        for field_name, field in root_type.fields.items():
            args_schema = (
                {arg_name: _describe_type(arg.type) for arg_name, arg in field.args.items()}
                if field.args
                else None
            )
            nodes.append({
                "kind": "graphql_field",
                "method": None,
                "path_template": None,
                "operation_id": None,
                "type_name": type_name,
                "field_name": field_name,
                "declared_request_schema": args_schema,
                "declared_response_schema": _describe_type(field.type),
            })
    return nodes
```

- [ ] **Step 4: Write `tests/test_graphql_schema.py`**

```python
import json
import socket
from pathlib import Path

import httpx
import pytest
import respx

from app.schema.graphql import (
    GraphQLFetchError,
    GraphQLValidationError,
    fetch_introspection,
    parse_graphql,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "countries-graphql-introspection.json").read_text()
)

SDL = """
type Query {
  pet(id: ID!): Pet
  pets(limit: Int): [Pet!]!
}

type Mutation {
  addPet(name: String!): Pet
}

type Pet {
  id: ID!
  name: String!
  tag: String
}
"""


def test_parse_real_countries_introspection_produces_real_nodes():
    nodes = parse_graphql(FIXTURE["data"])
    assert len(nodes) == 6  # the real API has exactly 6 Query fields, no Mutation type
    by_field = {(n["type_name"], n["field_name"]): n for n in nodes}
    assert ("Query", "countries") in by_field
    countries = by_field[("Query", "countries")]
    assert countries["kind"] == "graphql_field"
    assert countries["method"] is None
    assert countries["declared_response_schema"] == {
        "kind": "LIST", "nullable": False,
        "of": {"kind": "NAMED", "name": "Country", "nullable": False},
    }


def test_parse_sdl_produces_query_and_mutation_nodes():
    nodes = parse_graphql(SDL)
    by_field = {(n["type_name"], n["field_name"]): n for n in nodes}
    assert set(by_field) == {("Query", "pet"), ("Query", "pets"), ("Mutation", "addPet")}

    pet = by_field[("Query", "pet")]
    assert pet["declared_request_schema"] == {"id": {"kind": "NAMED", "name": "ID", "nullable": False}}
    assert pet["declared_response_schema"] == {"kind": "NAMED", "name": "Pet", "nullable": True}

    pets = by_field[("Query", "pets")]
    assert pets["declared_request_schema"] == {"limit": {"kind": "NAMED", "name": "Int", "nullable": True}}
    assert pets["declared_response_schema"] == {
        "kind": "LIST", "nullable": False,
        "of": {"kind": "NAMED", "name": "Pet", "nullable": False},
    }

    add_pet = by_field[("Mutation", "addPet")]
    assert add_pet["declared_request_schema"] == {"name": {"kind": "NAMED", "name": "String", "nullable": False}}


def test_invalid_sdl_raises_validation_error():
    with pytest.raises(GraphQLValidationError):
        parse_graphql("type Query { pet(id ID!): Pet }")


def test_invalid_introspection_payload_raises_validation_error():
    with pytest.raises(GraphQLValidationError):
        parse_graphql({"not": "valid"})


@respx.mock
def test_fetch_introspection_real_http_post(monkeypatch):
    # "example.invalid" is RFC 2606 reserved and never actually resolves --
    # respx mocks the HTTP layer but not DNS, so fake a public-IP resolution
    # for our own pre-fetch safety check (app/schema/openapi.py's is_safe_url).
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.post("https://example.invalid/graphql").mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    data = fetch_introspection("https://example.invalid/graphql")
    assert data == FIXTURE["data"]


def test_fetch_introspection_rejects_a_private_ip_target():
    with pytest.raises(GraphQLFetchError):
        fetch_introspection("http://127.0.0.1:9999/graphql")


@respx.mock
def test_fetch_introspection_graphql_errors_raise(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.post("https://example.invalid/graphql").mock(
        return_value=httpx.Response(200, json={"errors": [{"message": "nope"}]})
    )
    with pytest.raises(GraphQLFetchError):
        fetch_introspection("https://example.invalid/graphql")
```

- [ ] **Step 5: Run the tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_graphql_schema.py -v`
Expected: all pass (7 tests).

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all existing tests still pass too (the `openapi.py` rename must
not break `test_openapi_schema.py` or `test_workspace_routes.py`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schema/openapi.py backend/app/schema/graphql.py \
        backend/pyproject.toml backend/tests/fixtures/countries-graphql-introspection.json \
        backend/tests/test_graphql_schema.py
git commit -m "feat: real GraphQL introspection + SDL parsing (Phase 1b)"
```

---

### Task 2: Wire GraphQL into `POST /api/workspaces`

**Files:**
- Modify: `backend/app/models.py` (widen `Workspace.raw_schema`'s type hint
  — SDL is stored as plain text, not a JSON object)
- Modify: `backend/app/routes/workspaces.py`
- Test: `backend/tests/test_workspace_routes.py`

**Interfaces:**
- Consumes: Task 1's `GraphQLFetchError`, `GraphQLValidationError`,
  `fetch_introspection`, `parse_graphql` from `app.schema.graphql`.
- Produces: `POST /api/workspaces` now accepts `schema_kind: "graphql"` the
  same way it already accepts `"openapi"` — no other route or response
  shape changes. `GET /api/workspaces/{id}` needs no change: it already
  returns `type_name`/`field_name` generically for every node, and already
  filters to `path_template is not None` before computing REST edges (a
  Phase 1a fix), so GraphQL nodes render with no edges — a real, known,
  honest v1 limitation (GraphQL's own type-relationship graph shape is
  SPEC.md §8.3, Phase 2 frontend work), not a bug to fix here.

- [ ] **Step 1: Widen the `raw_schema` type hint**

In `backend/app/models.py`, change:

```python
    raw_schema: Mapped[dict] = mapped_column(JSONB)
```

to:

```python
    raw_schema: Mapped[dict | str] = mapped_column(JSONB)  # dict (OpenAPI/introspection) or str (pasted SDL)
```

This is a type-hint-only change — `JSONB` already stores a plain string
scalar with no schema migration needed (Postgres `jsonb` accepts any valid
JSON value, including a bare string).

- [ ] **Step 2: Rewrite the create-workspace branch**

In `backend/app/routes/workspaces.py`, replace the imports and the whole
body of `create_workspace` (keep `list_workspaces` and `get_workspace`
exactly as they are):

```python
from app.db import DEFAULT_USER_ID, get_session
from app.edges import compute_rest_edges
from app.models import Node, Workspace
from app.schema.graphql import GraphQLFetchError, GraphQLValidationError, fetch_introspection, parse_graphql
from app.schema.openapi import OpenAPIFetchError, OpenAPIValidationError, fetch_spec, parse_openapi

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.post("", status_code=201)
def create_workspace(body: dict, session: Session = Depends(get_session)) -> dict:
    name = body.get("name")
    schema_kind = body.get("schema_kind")
    url = body.get("schema_source_url")
    raw = body.get("raw_schema")
    if not name or schema_kind not in ("openapi", "graphql"):
        raise HTTPException(status_code=422, detail="name and schema_kind in ('openapi', 'graphql') are required")
    if bool(url) == bool(raw):
        raise HTTPException(status_code=422, detail="exactly one of schema_source_url or raw_schema is required")

    if schema_kind == "openapi":
        if url:
            try:
                spec = fetch_spec(url)
            except OpenAPIFetchError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
        else:
            spec = raw
        try:
            parsed_nodes = parse_openapi(spec)
        except OpenAPIValidationError as exc:
            raise HTTPException(status_code=422, detail=f"invalid OpenAPI spec: {exc}") from exc
    else:
        if url:
            try:
                spec = fetch_introspection(url)
            except GraphQLFetchError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
        else:
            if not isinstance(raw, str):
                raise HTTPException(
                    status_code=422, detail="raw_schema for schema_kind='graphql' must be an SDL string"
                )
            spec = raw
        try:
            parsed_nodes = parse_graphql(spec)
        except GraphQLValidationError as exc:
            raise HTTPException(status_code=422, detail=f"invalid GraphQL schema: {exc}") from exc

    workspace = Workspace(
        user_id=DEFAULT_USER_ID, name=name, schema_kind=schema_kind,
        schema_source=url or "pasted", raw_schema=spec,
    )
    session.add(workspace)
    session.flush()

    for pn in parsed_nodes:
        session.add(Node(workspace_id=workspace.id, **pn))
    session.commit()

    return {"id": workspace.id, "name": workspace.name, "schema_kind": workspace.schema_kind,
            "node_count": len(parsed_nodes)}
```

- [ ] **Step 3: Add GraphQL cases to `tests/test_workspace_routes.py`**

Add these test functions to the existing file (keep every existing test —
this only adds new ones). No new imports needed — `json`, `Path`, `httpx`,
`respx`, and `socket` are already imported at the top of this file.

```python
GRAPHQL_SDL = """
type Query {
  pet(id: ID!): Pet
}

type Pet {
  id: ID!
  name: String!
}
"""

GRAPHQL_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "countries-graphql-introspection.json").read_text()
)


def test_create_workspace_from_a_pasted_graphql_sdl():
    r = client.post("/api/workspaces", json={
        "name": "Pets (GraphQL)", "schema_kind": "graphql", "raw_schema": GRAPHQL_SDL,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["schema_kind"] == "graphql"
    assert body["node_count"] == 1


@respx.mock
def test_create_workspace_from_a_real_graphql_url(monkeypatch):
    # Reuses the same real, live-fetched introspection fixture Task 1's
    # test_graphql_schema.py verifies parse_graphql against directly --
    # a hand-rolled minimal introspection payload risks being rejected by
    # build_client_schema for a reason never actually checked against the
    # real library (e.g. a missing built-in scalar type entry).
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.post("https://example.invalid/graphql").mock(
        return_value=httpx.Response(200, json=GRAPHQL_FIXTURE)
    )
    r = client.post("/api/workspaces", json={
        "name": "Countries (GraphQL)", "schema_kind": "graphql",
        "schema_source_url": "https://example.invalid/graphql",
    })
    assert r.status_code == 201
    assert r.json()["node_count"] == 6


def test_create_workspace_rejects_a_non_string_graphql_raw_schema():
    r = client.post("/api/workspaces", json={
        "name": "bad", "schema_kind": "graphql", "raw_schema": {"not": "a string"},
    })
    assert r.status_code == 422


def test_create_workspace_rejects_invalid_schema_kind():
    r = client.post("/api/workspaces", json={
        "name": "x", "schema_kind": "soap", "raw_schema": "irrelevant",
    })
    assert r.status_code == 422
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 32 passed (21 prior + Task 1's 7 new + these 4 new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/app/routes/workspaces.py backend/tests/test_workspace_routes.py
git commit -m "feat: POST /api/workspaces accepts schema_kind=graphql"
```

---

### Task 3: Frontend — create and display GraphQL workspaces

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/components/WorkspaceForm.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/DetailPanel.tsx`
- Modify: `frontend/src/styles.css`
- Create: `frontend/src/lib/nodeLabel.ts`
- Test: `frontend/src/lib/nodeLabel.test.ts`

**Interfaces:**
- Consumes: Task 2's `POST /api/workspaces` (now accepts
  `schema_kind: 'graphql'`); the existing `Node`/`Workspace` shapes from
  `api.ts` (widened here, not restructured).
- Produces: `nodeLabel(node: Node): { eyebrow: string; title: string }` —
  the single place that decides whether a node's header line reads as REST
  (`method · path_template` / `operation_id`) or GraphQL
  (`type_name field` / `field_name`). `DetailPanel` consumes this instead
  of reading `node.method`/`node.path_template` directly.

- [ ] **Step 1: Widen `api.ts`'s types and `createWorkspace`**

In `frontend/src/api.ts`, replace the `Node`, `Workspace`, and
`WorkspaceSummary` interfaces' `kind`/`schema_kind` fields and
`createWorkspace`:

```typescript
export interface Node {
  id: string
  kind: 'rest_operation' | 'graphql_field'
  method: string | null
  path_template: string | null
  operation_id: string | null
  type_name: string | null
  field_name: string | null
  declared_request_schema: Record<string, unknown> | null
  declared_response_schema: Record<string, unknown> | null
  call_count: number
}

export interface Edge {
  from_node: string
  to_node: string
}

export interface Workspace {
  id: string
  name: string
  schema_kind: 'openapi' | 'graphql'
  nodes: Node[]
  edges: Edge[]
}

export interface WorkspaceSummary {
  id: string
  name: string
  schema_kind: Workspace['schema_kind']
}
```

And replace `createWorkspace`:

```typescript
export function createWorkspace(
  name: string,
  kind: 'openapi' | 'graphql',
  source: { url: string } | { rawSchema: object | string },
): Promise<{ id: string; name: string; schema_kind: string; node_count: number }> {
  const body =
    'url' in source
      ? { name, schema_kind: kind, schema_source_url: source.url }
      : { name, schema_kind: kind, raw_schema: source.rawSchema }
  return fetch('/api/workspaces', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then((res) => json<{ id: string; name: string; schema_kind: string; node_count: number }>(res))
}
```

(`listWorkspaces`, `getWorkspace`, `sendRequest` are unchanged.)

- [ ] **Step 2: Add a kind selector to `WorkspaceForm.tsx`**

Replace the whole file:

```tsx
import { useState } from 'react'

/** The real "give it a schema" entry point (SPEC.md §6 step 1) — a real
 * OpenAPI or GraphQL URL, submitted for real parsing. This form only
 * supports a URL today; raw-schema/SDL paste (`createWorkspace`'s
 * `rawSchema` branch) is a real, supported backend capability with no UI
 * yet. */
export function WorkspaceForm({ onCreate, busy }: {
  onCreate: (name: string, kind: 'openapi' | 'graphql', url: string) => void
  busy: boolean
}) {
  const [name, setName] = useState('')
  const [kind, setKind] = useState<'openapi' | 'graphql'>('openapi')
  const [url, setUrl] = useState('')

  return (
    <form
      className="workspace-form"
      onSubmit={(e) => {
        e.preventDefault()
        if (name.trim() && url.trim()) onCreate(name.trim(), kind, url.trim())
      }}
    >
      <input
        type="text" placeholder="Workspace name" value={name}
        onChange={(e) => setName(e.target.value)} disabled={busy} aria-label="Workspace name"
      />
      <select
        value={kind} onChange={(e) => setKind(e.target.value as 'openapi' | 'graphql')}
        disabled={busy} aria-label="Schema kind"
      >
        <option value="openapi">OpenAPI</option>
        <option value="graphql">GraphQL</option>
      </select>
      <input
        type="text"
        placeholder={kind === 'openapi' ? 'https://api.example.com/openapi.json' : 'https://api.example.com/graphql'}
        value={url}
        onChange={(e) => setUrl(e.target.value)} disabled={busy} aria-label="Schema URL"
      />
      <button type="submit" disabled={busy || !name.trim() || !url.trim()}>
        {busy ? 'Parsing…' : 'Create'}
      </button>
    </form>
  )
}
```

- [ ] **Step 3: Wire the kind through `App.tsx`**

In `frontend/src/App.tsx`, change `handleCreate`'s signature and its
`createWorkspace` call:

```typescript
  function handleCreate(name: string, kind: 'openapi' | 'graphql', url: string) {
    setBusy(true)
    setError(null)
    createWorkspace(name, kind, { url })
      .then((created) => getWorkspace(created.id))
      .then((ws) => { setWorkspace(ws); setStatuses({}) })
      .catch((e) => setError(String(e)))
      .finally(() => setBusy(false))
  }
```

And update the idle-hint copy (still in `App.tsx`) from:

```tsx
        {!workspace && !error && (
          <p className="idle-hint">Paste a real OpenAPI spec URL above to build its 3D map.</p>
        )}
```

to:

```tsx
        {!workspace && !error && (
          <p className="idle-hint">Paste a real OpenAPI or GraphQL URL above to build its 3D map.</p>
        )}
```

- [ ] **Step 4: Add `lib/nodeLabel.ts` and use it in `DetailPanel.tsx`**

Create `frontend/src/lib/nodeLabel.ts`:

```typescript
import type { Node } from '../api'

/** DetailPanel's "what is this node" header line, factored out so it's
 * testable without a DOM. node.kind decides which side of the REST/GraphQL
 * fields is the real one -- the other side is always null (SPEC.md §7.5). */
export function nodeLabel(node: Node): { eyebrow: string; title: string } {
  if (node.kind === 'graphql_field') {
    return { eyebrow: `${node.type_name} field`, title: node.field_name ?? '' }
  }
  return { eyebrow: `${node.method} · ${node.path_template}`, title: node.operation_id ?? '' }
}
```

In `frontend/src/components/DetailPanel.tsx`, add the import:

```typescript
import { nodeLabel } from '../lib/nodeLabel'
```

and replace:

```tsx
        <p className="eyebrow">{node.method} · {node.path_template}</p>
        <h3 id="detail-title" className="dive__title">{node.operation_id}</h3>
```

with:

```tsx
        <p className="eyebrow">{nodeLabel(node).eyebrow}</p>
        <h3 id="detail-title" className="dive__title">{nodeLabel(node).title}</h3>
```

- [ ] **Step 5: Style the new `<select>`**

In `frontend/src/styles.css`, right after the existing
`.workspace-form input{...}` rule, add:

```css
.workspace-form select{background:rgba(255,255,255,.04);border:1px solid var(--hair);
  color:var(--paper);font-family:var(--mono);font-size:11px;padding:9px 8px;
  border-radius:2px}
```

- [ ] **Step 6: Write `lib/nodeLabel.test.ts`**

```typescript
import { describe, expect, it } from 'vitest'
import type { Node } from '../api'
import { nodeLabel } from './nodeLabel'

const restNode: Node = {
  id: '1', kind: 'rest_operation', method: 'GET', path_template: '/pets/{id}',
  operation_id: 'getPet', type_name: null, field_name: null,
  declared_request_schema: null, declared_response_schema: null, call_count: 0,
}

const graphqlNode: Node = {
  id: '2', kind: 'graphql_field', method: null, path_template: null,
  operation_id: null, type_name: 'Query', field_name: 'pet',
  declared_request_schema: null, declared_response_schema: null, call_count: 0,
}

describe('nodeLabel', () => {
  it('labels a REST node by method and path', () => {
    expect(nodeLabel(restNode)).toEqual({ eyebrow: 'GET · /pets/{id}', title: 'getPet' })
  })

  it('labels a GraphQL node by type and field', () => {
    expect(nodeLabel(graphqlNode)).toEqual({ eyebrow: 'Query field', title: 'pet' })
  })
})
```

- [ ] **Step 7: Run the tests and type-check**

Run: `cd frontend && npx vitest run`
Expected: all pass (7 tests — 5 existing + 2 new).

Run: `cd frontend && npx tsc -b`
Expected: no errors.

Run: `cd frontend && npx vite build`
Expected: succeeds (the existing chunk-size warning for the 3D graph
library is expected, not a blocker).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api.ts frontend/src/components/WorkspaceForm.tsx \
        frontend/src/App.tsx frontend/src/components/DetailPanel.tsx \
        frontend/src/styles.css frontend/src/lib/nodeLabel.ts frontend/src/lib/nodeLabel.test.ts
git commit -m "feat: create/display GraphQL workspaces in the UI"
```

---

### Task 4: Live verification + `HANDOFF.md`

**Files:**
- Modify: `HANDOFF.md`

**Interfaces:**
- Consumes: Tasks 1-3's complete, committed GraphQL support. No new
  interfaces produced — this task verifies and documents.

- [ ] **Step 1: Start the real stack**

```bash
cd backend
docker compose up -d
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/alembic upgrade head
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/uvicorn app.main:app --port 8123 &
cd ../frontend && npm run dev &
```

- [ ] **Step 2: Live-verify in a real browser**

Open the app (`http://localhost:5173`). Create a workspace: name it
anything, select "GraphQL" in the kind selector, enter
`https://countries.trevorblades.com/graphql`, submit. Confirm:
- The backend fetches, parses, and persists 6 real nodes (no errors).
- The 3D graph renders 6 nodes (they'll cluster with no visible edges —
  the known, stated v1 limitation from this plan's Global Constraints).
- Clicking a node (e.g. `countries`) opens the detail panel showing
  `Query field` as the eyebrow and `countries` as the title (not `null ·
  null`), with its real declared argument/response type descriptors
  visible as JSON.
- Clicking Send still returns the honest 501 (Phase 2's job, unchanged).

Also confirm the OpenAPI path still works end-to-end (no regression):
create a second workspace with kind "OpenAPI" and
`https://petstore3.swagger.io/api/v3/openapi.json`.

- [ ] **Step 3: Update `HANDOFF.md`**

Append a new `## Phase 1b: GraphQL Schema Parsing` section (after the
existing Phase 1a section), following that section's own structure
(What/Why, What was built, Known simplifications, Verified, Next). It must
state plainly:
- Real GraphQL introspection (`fetch_introspection`) and SDL parsing
  (`parse_graphql`) via `graphql-core`, one `Node` per `Query`/`Mutation`
  field, `Subscription` explicitly out of scope.
- The real public API used for live verification
  (`https://countries.trevorblades.com/graphql`) and the real test counts:
  backend 21 → 32 (Task 1's 7 new + Task 2's 4 new), frontend 5 → 7 (Task
  3's 2 new) — these are the exact expected totals from this plan's own
  task steps; copy the actual numbers from Task 2 Step 4's and Task 3 Step
  7's real `pytest`/`vitest` output into HANDOFF.md rather than these.
- The still-open, explicitly-named gaps: no workspace-list/picker UI
  (carried over from Phase 1a, still true), and GraphQL nodes render with
  no edges yet (a real type-relationship graph layout for GraphQL mode is
  SPEC.md §8.3 frontend work, not attempted here).
- Next: Phase 2 (SPEC.md §10-11) — real request execution against both
  REST and GraphQL targets, the full SSRF-hardened proxy, and real
  drift-checking (response vs. declared schema).

- [ ] **Step 4: Commit**

```bash
git add HANDOFF.md
git commit -m "docs: Phase 1b HANDOFF — GraphQL parsing live-verified"
```
