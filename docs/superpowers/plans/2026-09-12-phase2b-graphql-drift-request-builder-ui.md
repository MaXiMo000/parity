# Phase 2b: GraphQL Drift-Checking + Real Request-Builder UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete SPEC.md's Phase 2 (SPEC.md §10: "real drift validation for both protocols") by adding GraphQL request-matching + drift-checking to the backend, and replace the frontend's currently-honestly-broken Send button with the real request-builder + curl-paste + history chrome SPEC.md §8.4 describes.

**Architecture:** A real GraphQL request is a POST with a JSON body carrying a `query` string — `app/matching.py` gains `match_graphql_node`, which parses that query with `graphql-core` (already a dependency, used identically to Phase 1b's introspection parsing) and matches the operation type + first selected field to a `Node`. `app/drift/graphql.py` gains `check_graphql_drift`, a recursive type-shape check against the `{kind, name/of, nullable}` descriptor Phase 1b's `_describe_type` already produces — deliberately NOT graphql-core's execution-result validation machinery, which needs resolvers this project doesn't have (SPEC.md §13's own stated "lighter custom shape-check" option). On the frontend, a new `RequestBuilder` component (method/url/headers/body fields, a curl-paste box that calls the already-real `/api/curl-parse`) replaces the old bare Send button inside `DetailPanel`, and a new `HistoryPanel` adds the workspace-wide history view SPEC.md §8.4 names.

**Tech Stack:** `graphql-core` (already a dependency, `parse()` verified against real query shapes below). No new frontend dependency — the request-builder is a plain form, matching this whole project's "plain CSS, no component library" restraint (SPEC.md §8.1).

**Spec:** [`SPEC.md`](../../../SPEC.md) §6 (steps 6-7, the GraphQL side of matching/validation), §7.5 (drift_finding's 4-state enum), §8.3 (the detail panel showing "the receipt, not a claim"), §8.4 (request builder, curl-paste toggle, history view), §13 (GraphQL response validation depth — the "lighter custom shape-check" decision this plan makes for real).

## Global Constraints

- **Verified against the real installed `graphql-core` (2026-09-12), not remembered behavior:**
  - `parse(query_text)` correctly extracts the operation type (`OperationDefinitionNode.operation.value`, e.g. `"query"`/`"mutation"`) and the first top-level selected field name, for both explicit (`query { ... }`) and shorthand (`{ ... }`) syntax. A mutation requires the explicit `mutation { ... }` form — shorthand is query-only, confirmed against the real parser.
  - A malformed query string raises `graphql.GraphQLSyntaxError` — caught and treated as "no match" (honest, not a crash), the same discipline this project already applies to a request matching no known node.
- **v1 scope, stated plainly (matching this project's "state the real simplification" discipline throughout):** GraphQL matching only looks at the FIRST operation definition and its FIRST top-level field selection in a request body — a real, deliberate simplification for the common case (one curl-pasted request, one operation, one top-level field). A request with multiple operations or multiple top-level fields in one query still fires for real and gets recorded, just matched (or not) by that first field alone.
- **GraphQL drift-checking only validates scalar leaf types precisely** (`Int`, `Float`, `String`, `ID`, `Boolean`) **and null-appropriateness at every level** (including inside a `LIST`). A custom object/enum type at the top level is only checked for presence and null-appropriateness, not deep-validated field-by-field — because `declared_response_schema` for a GraphQL node only stores that field's own return-type descriptor (from Phase 1b), not a full recursive schema of the object type it names. This is SPEC.md §13's own "lighter custom shape-check" option, chosen over graphql-core's execution-result validation (which needs resolvers this project doesn't have) — stated here as a real, deliberate scope boundary, not silently implied as deeper than it is.
- **`Workspace.schema_source` and `Workspace.base_path` are both now exposed on `GET /api/workspaces/{id}`** (`base_path` already was, since Phase 2a; `schema_source` is newly added in this plan, Task 1) — the frontend's request-builder needs a real starting URL to pre-fill, and `schema_source` (the URL the schema was originally fetched from, or `"pasted"`) is the only real signal this project has for "what host is this API actually on." This is a UX convenience, not a security boundary — the backend's own SSRF guard (already real, already reviewed) is what actually protects the outbound fetch regardless of what the frontend pre-fills.

---

### Task 1: GraphQL request-matching + drift-checking (backend)

**Files:**
- Modify: `backend/app/matching.py` (add `match_graphql_node`, alongside the existing `match_rest_node`)
- Create: `backend/app/drift/graphql.py`
- Modify: `backend/app/routes/requests.py` (wire both into `send_request`)
- Modify: `backend/app/routes/workspaces.py` (expose `schema_source` in `get_workspace`)
- Test: `backend/tests/test_matching.py` (add GraphQL matching tests)
- Test: `backend/tests/test_drift_graphql.py` (new)
- Test: `backend/tests/test_request_routes.py` (add GraphQL end-to-end route tests)
- Test: `backend/tests/test_workspace_routes.py` (assert `schema_source` is present)

**Interfaces:**
- Produces: `match_graphql_node(nodes: list[dict], request_body_text: str | None) -> dict | None` in `app.matching` (each `nodes` entry needs at least `id`, `type_name`, `field_name`). `check_graphql_drift(declared_response_schema: dict | None, response_body_text: str | None) -> tuple[str, str | None]` in `app.drift.graphql` — same `(status, detail)` return shape as `check_rest_drift`.

- [ ] **Step 1: Add `match_graphql_node` to `app/matching.py`**

Add this import at the top of the file, alongside the existing one:

```python
import json

from graphql import GraphQLSyntaxError, OperationDefinitionNode, parse
```

Add this function at the end of the file, after `match_rest_node`:

```python
def match_graphql_node(nodes: list[dict], request_body_text: str | None) -> dict | None:
    """Parses the real GraphQL-over-HTTP request body (the standard JSON
    envelope: {"query": "...", "variables": {...}}) and matches its
    operation type + first top-level selected field to a Node (SPEC.md
    §6 step 6, GraphQL side). `nodes` are GraphQL node dicts carrying at
    least `id`, `type_name`, `field_name`. Returns None -- never a guess
    -- if the body isn't valid JSON, has no string "query" field, the
    query doesn't parse as valid GraphQL, the document has no real
    operation definition, or no node matches. v1 scope: only the FIRST
    operation definition and its FIRST top-level field selection are
    considered (SPEC.md's own stated simplification for the common
    single-operation, single-field case)."""
    if not request_body_text:
        return None
    try:
        envelope = json.loads(request_body_text)
    except ValueError:
        return None
    query_text = envelope.get("query") if isinstance(envelope, dict) else None
    if not isinstance(query_text, str):
        return None
    try:
        document = parse(query_text)
    except GraphQLSyntaxError:
        return None
    for definition in document.definitions:
        if not isinstance(definition, OperationDefinitionNode):
            continue
        type_name = definition.operation.value.capitalize()  # "query" -> "Query", "mutation" -> "Mutation"
        if not definition.selection_set.selections:
            return None
        first_selection = definition.selection_set.selections[0]
        field_name_node = getattr(first_selection, "name", None)
        if field_name_node is None:
            return None
        field_name = field_name_node.value
        for node in nodes:
            if node.get("type_name") == type_name and node.get("field_name") == field_name:
                return node
        return None
    return None
```

- [ ] **Step 2: Add GraphQL matching tests to `tests/test_matching.py`**

Add these test functions at the end of the file:

```python
from app.matching import match_graphql_node

GRAPHQL_NODES = [
    {"id": "queryPet", "type_name": "Query", "field_name": "pet"},
    {"id": "queryPets", "type_name": "Query", "field_name": "pets"},
    {"id": "mutationAddPet", "type_name": "Mutation", "field_name": "addPet"},
]


def test_matches_a_real_query_by_operation_and_field():
    import json
    body = json.dumps({"query": "{ pet(id: 1) { name } }"})
    result = match_graphql_node(GRAPHQL_NODES, body)
    assert result["id"] == "queryPet"


def test_matches_an_explicit_mutation():
    import json
    body = json.dumps({"query": "mutation { addPet(name: \"Rex\") { id } }"})
    result = match_graphql_node(GRAPHQL_NODES, body)
    assert result["id"] == "mutationAddPet"


def test_no_match_when_the_field_is_unknown():
    import json
    body = json.dumps({"query": "{ totallyUnknownField }"})
    assert match_graphql_node(GRAPHQL_NODES, body) is None


def test_no_match_on_malformed_graphql():
    import json
    body = json.dumps({"query": "not valid graphql {{{"})
    assert match_graphql_node(GRAPHQL_NODES, body) is None


def test_no_match_when_body_is_not_json():
    assert match_graphql_node(GRAPHQL_NODES, "not json at all") is None


def test_no_match_when_body_has_no_query_field():
    import json
    assert match_graphql_node(GRAPHQL_NODES, json.dumps({"notQuery": "x"})) is None


def test_no_match_when_body_is_empty():
    assert match_graphql_node(GRAPHQL_NODES, None) is None
    assert match_graphql_node(GRAPHQL_NODES, "") is None
```

- [ ] **Step 3: Write `app/drift/graphql.py`**

```python
"""Validates a real GraphQL response against a node's declared return
type (SPEC.md §6 step 7, GraphQL side; §13's "lighter custom shape-check"
option, chosen over graphql-core's execution-result validation machinery
-- that needs real resolvers this project doesn't have). Checks scalar
leaf types precisely and null-appropriateness at every level; a custom
object/enum type is only checked for presence and null-appropriateness,
not deep-validated field-by-field, since declared_response_schema only
stores that field's own return-type descriptor (Phase 1b), not a full
recursive schema of the type it names -- a real, stated v1 scope
boundary, not silently implied as deeper than it is."""

from __future__ import annotations

import json
from typing import Any

_SCALAR_CHECKS = {
    "Int": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "Float": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "String": lambda v: isinstance(v, str),
    "ID": lambda v: isinstance(v, str) or isinstance(v, int),
    "Boolean": lambda v: isinstance(v, bool),
}


def _check_type_shape(value: Any, descriptor: dict[str, Any], path: str) -> str | None:
    if value is None:
        if descriptor.get("nullable", True):
            return None
        return f"{path}: null is not allowed (declared non-nullable)"
    kind = descriptor["kind"]
    if kind == "LIST":
        if not isinstance(value, list):
            return f"{path}: expected a list, got {type(value).__name__}"
        for i, item in enumerate(value):
            detail = _check_type_shape(item, descriptor["of"], f"{path}[{i}]")
            if detail:
                return detail
        return None
    name = descriptor.get("name")
    check = _SCALAR_CHECKS.get(name)
    if check is not None and not check(value):
        return f"{path}: expected {name}, got {type(value).__name__}"
    return None


def check_graphql_drift(declared_response_schema: dict[str, Any] | None, response_body_text: str | None) -> tuple[str, str | None]:
    """Returns (status, detail). status is one of "matched", "violated",
    or "unverified_no_schema" (no declared schema to check against)."""
    if declared_response_schema is None:
        return "unverified_no_schema", None
    try:
        payload = json.loads(response_body_text) if response_body_text else None
    except ValueError:
        return "violated", "response body is not valid JSON"
    if not isinstance(payload, dict):
        return "violated", "response body is not a JSON object"
    if payload.get("errors"):
        return "violated", f"response contained GraphQL errors: {payload['errors']}"
    data = payload.get("data")
    if not isinstance(data, dict) or not data:
        return "violated", "response has no 'data' field to check"
    field_name, value = next(iter(data.items()))
    detail = _check_type_shape(value, declared_response_schema, f"data.{field_name}")
    if detail:
        return "violated", detail
    return "matched", None
```

- [ ] **Step 4: Write `tests/test_drift_graphql.py`**

```python
import json

from app.drift.graphql import check_graphql_drift

LIST_SCHEMA = {"kind": "LIST", "of": {"kind": "NAMED", "name": "Country", "nullable": False}, "nullable": False}
NAMED_NULLABLE_SCHEMA = {"kind": "NAMED", "name": "Country", "nullable": True}
INT_SCHEMA = {"kind": "NAMED", "name": "Int", "nullable": False}


def test_no_declared_schema_is_unverified_no_schema():
    status, detail = check_graphql_drift(None, json.dumps({"data": {"x": 1}}))
    assert status == "unverified_no_schema"


def test_matching_list_response_is_matched():
    body = json.dumps({"data": {"countries": [{"code": "US"}, {"code": "FR"}]}})
    status, detail = check_graphql_drift(LIST_SCHEMA, body)
    assert status == "matched"


def test_null_where_non_nullable_is_violated():
    body = json.dumps({"data": {"countries": None}})
    status, detail = check_graphql_drift(LIST_SCHEMA, body)
    assert status == "violated"
    assert "null is not allowed" in detail


def test_non_list_where_list_declared_is_violated():
    body = json.dumps({"data": {"countries": {"code": "US"}}})
    status, detail = check_graphql_drift(LIST_SCHEMA, body)
    assert status == "violated"
    assert "expected a list" in detail


def test_null_where_nullable_named_is_matched():
    body = json.dumps({"data": {"country": None}})
    status, detail = check_graphql_drift(NAMED_NULLABLE_SCHEMA, body)
    assert status == "matched"


def test_wrong_scalar_type_is_violated():
    body = json.dumps({"data": {"count": "not-an-int"}})
    status, detail = check_graphql_drift(INT_SCHEMA, body)
    assert status == "violated"
    assert "Int" in detail


def test_graphql_errors_in_the_response_are_violated():
    body = json.dumps({"errors": [{"message": "field not found"}], "data": None})
    status, detail = check_graphql_drift(INT_SCHEMA, body)
    assert status == "violated"
    assert "GraphQL errors" in detail


def test_non_json_body_is_violated():
    status, detail = check_graphql_drift(INT_SCHEMA, "not json")
    assert status == "violated"
    assert "not valid JSON" in detail


def test_custom_object_type_is_matched_without_deep_validation():
    # Country is a custom object type -- v1 only checks presence/nullability,
    # not Country's own fields (see this task's own stated scope boundary).
    body = json.dumps({"data": {"country": {"anything": "goes", "here": 123}}})
    status, detail = check_graphql_drift(NAMED_NULLABLE_SCHEMA, body)
    assert status == "matched"
```

- [ ] **Step 5: Wire both into `app/routes/requests.py`**

Add to the imports at the top:

```python
from app.drift.graphql import check_graphql_drift
from app.matching import match_graphql_node, match_rest_node
```

(This replaces the existing `from app.matching import match_rest_node` line — just add `match_graphql_node` to it.)

Change the node-matching block from:

```python
    node: Node | None = None
    if workspace.schema_kind == "openapi":
        node_dicts = [
            {"id": n.id, "method": n.method, "path_template": n.path_template}
            for n in workspace.nodes
        ]
        matched = match_rest_node(node_dicts, method, url, workspace.base_path)
        if matched:
            node = session.get(Node, matched["id"])
```

to:

```python
    node: Node | None = None
    if workspace.schema_kind == "openapi":
        node_dicts = [
            {"id": n.id, "method": n.method, "path_template": n.path_template}
            for n in workspace.nodes
        ]
        matched = match_rest_node(node_dicts, method, url, workspace.base_path)
        if matched:
            node = session.get(Node, matched["id"])
    elif workspace.schema_kind == "graphql":
        graphql_node_dicts = [
            {"id": n.id, "type_name": n.type_name, "field_name": n.field_name}
            for n in workspace.nodes
        ]
        graphql_matched = match_graphql_node(graphql_node_dicts, req_body)
        if graphql_matched:
            node = session.get(Node, graphql_matched["id"])
```

Change the drift-checking block from:

```python
    if node is not None:
        node.call_count += 1
        if resp.status_code == 204:
            status, detail = "unverified_no_schema", "204 No Content has no body to validate against a declared schema"
        elif not (200 <= resp.status_code < 300):
            status, detail = "unverified_no_schema", f"non-2xx response ({resp.status_code}); only 2xx response schemas are declared (SPEC.md §7.2)"
        else:
            status, detail = check_rest_drift(node.declared_response_schema, resp.text)
    else:
        status, detail = "unverified_no_match", None
```

to:

```python
    if node is not None:
        node.call_count += 1
        if resp.status_code == 204:
            status, detail = "unverified_no_schema", "204 No Content has no body to validate against a declared schema"
        elif not (200 <= resp.status_code < 300):
            status, detail = "unverified_no_schema", f"non-2xx response ({resp.status_code}); only 2xx response schemas are declared (SPEC.md §7.2)"
        elif node.kind == "graphql_field":
            status, detail = check_graphql_drift(node.declared_response_schema, resp.text)
        else:
            status, detail = check_rest_drift(node.declared_response_schema, resp.text)
    else:
        status, detail = "unverified_no_match", None
```

- [ ] **Step 6: Expose `schema_source` in `GET /api/workspaces/{id}`**

In `backend/app/routes/workspaces.py`, `get_workspace`, change:

```python
    return {
        "id": workspace.id, "name": workspace.name, "schema_kind": workspace.schema_kind,
        "base_path": workspace.base_path,
        "nodes": node_dicts,
        "edges": [{"from_node": a, "to_node": b} for a, b in edges],
    }
```

to:

```python
    return {
        "id": workspace.id, "name": workspace.name, "schema_kind": workspace.schema_kind,
        "base_path": workspace.base_path, "schema_source": workspace.schema_source,
        "nodes": node_dicts,
        "edges": [{"from_node": a, "to_node": b} for a, b in edges],
    }
```

In `backend/tests/test_workspace_routes.py`, in `test_list_and_get_real_workspace`, add this assertion right after the existing `assert got["base_path"] == "/api/v3"` line:

```python
    assert got["schema_source"] == "pasted"  # this test creates the workspace via raw_schema, not a URL
```

- [ ] **Step 7: Add GraphQL end-to-end route tests to `tests/test_request_routes.py`**

Add these two tests at the end of the file (reuse the existing `_fake_getaddrinfo` helper already in this file):

```python
@respx.mock
def test_send_a_real_graphql_request_that_matches_and_drifts(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Pets (GraphQL)", "schema_kind": "graphql",
        "raw_schema": "type Query { pet(id: ID!): Pet } type Pet { id: ID! name: String! }",
    }).json()

    respx.post("https://93.184.216.34/graphql").mock(
        return_value=httpx.Response(200, json={"data": {"pet": "not-an-object"}})
    )
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "POST", "url": "https://example.invalid/graphql",
        "headers": {}, "body": '{"query": "{ pet(id: 1) { name } }"}',
    })
    assert r.status_code == 201
    body = r.json()
    assert body["request"]["node_id"] is not None
    # declared type for `pet` is a nullable NAMED "Pet" (a custom object type) --
    # v1 GraphQL drift-checking only checks presence/nullability for a custom
    # object type, so a string value here is NOT flagged (matches this task's
    # own stated scope boundary -- confirmed real, not a bug).
    assert body["drift_finding"]["status"] == "matched"


@respx.mock
def test_send_a_graphql_request_that_matches_no_field_is_unverified_no_match(monkeypatch):
    _fake_getaddrinfo(monkeypatch)
    ws = client.post("/api/workspaces", json={
        "name": "Pets (GraphQL)", "schema_kind": "graphql",
        "raw_schema": "type Query { pet(id: ID!): Pet } type Pet { id: ID! name: String! }",
    }).json()
    respx.post("https://93.184.216.34/graphql").mock(return_value=httpx.Response(200, json={"data": {"totallyUnknown": 1}}))
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={
        "method": "POST", "url": "https://example.invalid/graphql",
        "headers": {}, "body": '{"query": "{ totallyUnknown }"}',
    })
    assert r.status_code == 201
    body = r.json()
    assert body["request"]["node_id"] is None
    assert body["drift_finding"]["status"] == "unverified_no_match"
```

- [ ] **Step 8: Run the tests**

Run: `cd backend && docker compose up -d && .venv/bin/python -m pytest -q`
Expected: all pass — report the real total (91 prior + 7 matching + 9 drift + 2 route + 1 workspace-route assertion — the assertion isn't a new test function, so expect roughly 91 + 18 = 109; confirm the real number from the actual output).

- [ ] **Step 9: Commit**

```bash
git add backend/app/matching.py backend/app/drift/graphql.py backend/app/routes/requests.py \
        backend/app/routes/workspaces.py backend/tests/test_matching.py backend/tests/test_drift_graphql.py \
        backend/tests/test_request_routes.py backend/tests/test_workspace_routes.py
git commit -m "feat: real GraphQL request-matching and drift-checking (completes SPEC.md Phase 2)"
```

---

### Task 2: The real request-builder UI (frontend)

**Files:**
- Modify: `frontend/src/api.ts`
- Create: `frontend/src/components/RequestBuilder.tsx`
- Modify: `frontend/src/components/DetailPanel.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/components/RequestBuilder.test.ts` (a pure-logic test file — see Step 6)

**Interfaces:**
- Produces: `<RequestBuilder workspace={Workspace} node={Node} onSent={(result: SendResult) => void} />` — a self-contained method/url/headers/body form with a curl-paste box, replacing `DetailPanel`'s old bare Send button. `DetailPanel` now takes `workspace: Workspace | null` and `onSent: (nodeId: string, result: SendResult) => void` instead of the old `onSend: (nodeId: string) => Promise<SendResult>`.

- [ ] **Step 1: Widen `api.ts`'s types and replace `sendRequest`**

Replace the `Workspace`, `SendResult` interfaces and `sendRequest` function. Change:

```typescript
export interface Workspace {
  id: string
  name: string
  schema_kind: 'openapi' | 'graphql'
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
  nodes: Node[]
  edges: Edge[]
}
```

Change:

```typescript
export interface SendResult {
  request: { node_id: string; method: string; url: string }
  response: { status_code: number; body: unknown }
  drift_finding: { status: 'matched' | 'violated'; detail: string }
}
```

to:

```typescript
export interface SendResult {
  request: { id: string; node_id: string | null; method: string; url: string }
  response: { id: string; status_code: number; body: unknown; latency_ms: number }
  drift_finding: { id: string; status: DriftStatus; detail: string | null }
}

export interface CurlParseResult {
  method: string
  url: string
  headers: Record<string, string>
  body: string | null
}

export interface NodeHistoryEntry {
  id: string
  status: DriftStatus
  detail: string | null
  created_at: string
}

export interface RequestHistoryEntry {
  id: string
  node_id: string | null
  method: string
  url: string
  sent_at: string
}
```

Add this import at the top of the file:

```typescript
import type { DriftStatus } from './lib/severity'
```

Change:

```typescript
export function sendRequest(workspaceId: string, nodeId: string): Promise<SendResult> {
  return fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/requests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ node_id: nodeId }),
  }).then((res) => json<SendResult>(res))
}
```

to:

```typescript
export function sendRequest(
  workspaceId: string,
  method: string,
  url: string,
  headers: Record<string, string>,
  body: string | null,
): Promise<SendResult> {
  return fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/requests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ method, url, headers, body }),
  }).then((res) => json<SendResult>(res))
}

export function curlParse(curl: string): Promise<CurlParseResult> {
  return fetch('/api/curl-parse', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ curl }),
  }).then((res) => json<CurlParseResult>(res))
}

export function getNodeHistory(workspaceId: string, nodeId: string): Promise<NodeHistoryEntry[]> {
  return fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/nodes/${encodeURIComponent(nodeId)}/history`)
    .then((res) => json<NodeHistoryEntry[]>(res))
}

export function getWorkspaceRequests(workspaceId: string): Promise<RequestHistoryEntry[]> {
  return fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/requests`)
    .then((res) => json<RequestHistoryEntry[]>(res))
}
```

- [ ] **Step 2: Create `components/RequestBuilder.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { curlParse, sendRequest, type Node, type SendResult, type Workspace } from '../api'

const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']

/** Best-effort starting URL for a node's request -- a UX convenience,
 * not a security boundary (the backend's own SSRF guard is what
 * actually protects the outbound fetch regardless of what this pre-fills).
 * REST: origin(schema_source) + base_path + path_template. GraphQL: the
 * schema_source itself, since a GraphQL endpoint usually IS the API
 * (unlike OpenAPI's spec-doc-vs-API-host distinction). Falls back to an
 * empty string (the user fills it in) when schema_source isn't a real URL
 * (a pasted spec) or doesn't parse. */
function guessUrl(workspace: Workspace, node: Node): string {
  if (!workspace.schema_source || !workspace.schema_source.startsWith('http')) return ''
  try {
    const origin = new URL(workspace.schema_source).origin
    if (node.kind === 'rest_operation' && node.path_template) {
      return `${origin}${workspace.base_path}${node.path_template}`
    }
    if (node.kind === 'graphql_field') {
      return workspace.schema_source
    }
  } catch {
    // malformed schema_source -- fall through to empty
  }
  return ''
}

function guessBody(node: Node): string {
  if (node.kind !== 'graphql_field') return ''
  const query = node.type_name === 'Mutation' ? `mutation { ${node.field_name} }` : `{ ${node.field_name} }`
  return JSON.stringify({ query }, null, 2)
}

export function RequestBuilder({ workspace, node, onSent }: {
  workspace: Workspace
  node: Node
  onSent: (result: SendResult) => void
}) {
  const [method, setMethod] = useState(node.method ?? (node.kind === 'graphql_field' ? 'POST' : 'GET'))
  const [url, setUrl] = useState(() => guessUrl(workspace, node))
  const [headersText, setHeadersText] = useState('')
  const [body, setBody] = useState(() => guessBody(node))
  const [curlText, setCurlText] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setMethod(node.method ?? (node.kind === 'graphql_field' ? 'POST' : 'GET'))
    setUrl(guessUrl(workspace, node))
    setHeadersText('')
    setBody(guessBody(node))
    setCurlText('')
    setError(null)
  }, [node.id, workspace.id])

  function parseHeadersText(): Record<string, string> {
    const headers: Record<string, string> = {}
    for (const line of headersText.split('\n')) {
      const idx = line.indexOf(':')
      if (idx > 0) headers[line.slice(0, idx).trim()] = line.slice(idx + 1).trim()
    }
    return headers
  }

  async function handleParseCurl() {
    setError(null)
    try {
      const parsed = await curlParse(curlText)
      setMethod(parsed.method)
      setUrl(parsed.url)
      setHeadersText(Object.entries(parsed.headers).map(([k, v]) => `${k}: ${v}`).join('\n'))
      setBody(parsed.body ?? '')
    } catch (e) {
      setError(String(e))
    }
  }

  async function handleSend() {
    setSending(true)
    setError(null)
    try {
      const result = await sendRequest(workspace.id, method, url, parseHeadersText(), body || null)
      onSent(result)
    } catch (e) {
      setError(String(e))
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="request-builder">
      <textarea
        className="request-builder__curl"
        placeholder="Paste a curl command…"
        value={curlText}
        onChange={(e) => setCurlText(e.target.value)}
      />
      <button type="button" className="request-builder__parse" onClick={handleParseCurl} disabled={!curlText.trim()}>
        Parse curl
      </button>

      <div className="request-builder__line">
        <select value={method} onChange={(e) => setMethod(e.target.value)} aria-label="HTTP method">
          {METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <input
          type="text" placeholder="https://api.example.com/…" value={url}
          onChange={(e) => setUrl(e.target.value)} aria-label="Request URL"
        />
      </div>
      <textarea
        className="request-builder__headers"
        placeholder="Header: value (one per line)"
        value={headersText}
        onChange={(e) => setHeadersText(e.target.value)}
        aria-label="Request headers"
      />
      <textarea
        className="request-builder__body"
        placeholder="Request body"
        value={body}
        onChange={(e) => setBody(e.target.value)}
        aria-label="Request body"
      />

      {error && <p className="dive__detail" style={{ color: 'var(--violate)' }}>{error}</p>}

      <button type="button" className="dive__send" onClick={handleSend} disabled={sending || !url.trim()}>
        {sending ? 'Sending…' : 'Send'}
      </button>
    </div>
  )
}
```

- [ ] **Step 3: Rewrite `DetailPanel.tsx`**

Replace the whole file:

```tsx
import { useEffect, useState } from 'react'
import { getNodeHistory, type Node, type NodeHistoryEntry, type SendResult, type Workspace } from '../api'
import { nodeLabel } from '../lib/nodeLabel'
import type { DriftStatus } from '../lib/severity'
import { useModalPanel } from '../lib/useModalPanel'
import { RequestBuilder } from './RequestBuilder'

export function DetailPanel({ workspace, node, status, onClose, onSent }: {
  workspace: Workspace | null
  node: Node | null
  status: DriftStatus
  onClose: () => void
  onSent: (nodeId: string, result: SendResult) => void
}) {
  const closeRef = useModalPanel(node !== null, onClose)
  const [result, setResult] = useState<SendResult | null>(null)
  const [history, setHistory] = useState<NodeHistoryEntry[]>([])

  useEffect(() => {
    setResult(null)
    if (workspace && node) {
      getNodeHistory(workspace.id, node.id).then(setHistory).catch(() => setHistory([]))
    } else {
      setHistory([])
    }
  }, [node?.id, workspace?.id])

  if (!node || !workspace) return null

  function handleSent(sendResult: SendResult) {
    setResult(sendResult)
    onSent(node!.id, sendResult)
    getNodeHistory(workspace!.id, node!.id).then(setHistory).catch(() => {})
  }

  return (
    <div className="dive-backdrop" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="dive" role="dialog" aria-modal="true" aria-labelledby="detail-title">
        <button type="button" className="dive__close" onClick={onClose} ref={closeRef} aria-label="Close detail panel">
          Close ✕
        </button>
        <p className="eyebrow">{nodeLabel(node).eyebrow}</p>
        <h3 id="detail-title" className="dive__title">{nodeLabel(node).title}</h3>
        <p className={`dive__status dive__status--${status}`}>{status}</p>

        <RequestBuilder workspace={workspace} node={node} onSent={handleSent} />

        {result && (
          <div className="dive__result">
            <p className="dive__label">Response ({result.response.status_code})</p>
            <pre className="dive__schema">{JSON.stringify(result.response.body, null, 2)}</pre>
            <p className={`dive__status dive__status--${result.drift_finding.status}`}>
              {result.drift_finding.status}
            </p>
            <p className="dive__detail">{result.drift_finding.detail}</p>
          </div>
        )}

        {node.declared_request_schema && (
          <>
            <p className="dive__label">Declared request</p>
            <pre className="dive__schema">{JSON.stringify(node.declared_request_schema, null, 2)}</pre>
          </>
        )}
        {node.declared_response_schema && (
          <>
            <p className="dive__label">Declared response</p>
            <pre className="dive__schema">{JSON.stringify(node.declared_response_schema, null, 2)}</pre>
          </>
        )}

        {history.length > 0 && (
          <>
            <p className="dive__label">History</p>
            <ul className="dive__history">
              {history.map((h) => (
                <li key={h.id} className={`dive__status dive__status--${h.status}`}>
                  {h.status} · {new Date(h.created_at).toLocaleString()}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Wire `App.tsx`**

Change the `handleSend` function (and its `sendRequest` import) from:

```typescript
import { createWorkspace, getWorkspace, sendRequest, type Workspace } from './api'
```

to:

```typescript
import { createWorkspace, getWorkspace, type SendResult, type Workspace } from './api'
```

Replace:

```typescript
  async function handleSend(nodeId: string) {
    if (!workspace) throw new Error('no workspace loaded')
    const result = await sendRequest(workspace.id, nodeId)
    setStatuses((prev) => ({ ...prev, [nodeId]: result.drift_finding.status }))
    return result
  }
```

with:

```typescript
  function handleSent(nodeId: string, result: SendResult) {
    setStatuses((prev) => ({ ...prev, [nodeId]: result.drift_finding.status }))
  }
```

Change the `<DetailPanel .../>` call from:

```tsx
      <DetailPanel node={selected} status={selectedId ? (statuses[selectedId] ?? 'unverified_no_schema') : 'unverified_no_schema'} onClose={handleClose} onSend={handleSend} />
```

to:

```tsx
      <DetailPanel workspace={workspace} node={selected} status={selectedId ? (statuses[selectedId] ?? 'unverified_no_schema') : 'unverified_no_schema'} onClose={handleClose} onSent={handleSent} />
```

- [ ] **Step 5: Style the new request-builder and history list**

Append to `frontend/src/styles.css`:

```css
.request-builder{display:flex;flex-direction:column;gap:6px;margin:14px 0}
.request-builder__curl{background:rgba(255,255,255,.03);border:1px solid var(--hair);
  color:var(--paper);font-family:var(--mono);font-size:11px;padding:8px;border-radius:2px;
  min-height:44px;resize:vertical}
.request-builder__parse{align-self:flex-start;background:transparent;border:1px solid var(--hair);
  color:var(--mute);font-family:var(--mono);font-size:10px;padding:6px 12px;border-radius:2px;cursor:pointer}
.request-builder__parse:hover:not(:disabled){border-color:var(--match);color:var(--match)}
.request-builder__parse:disabled{opacity:.5;cursor:not-allowed}
.request-builder__line{display:flex;gap:6px}
.request-builder__line select{background:rgba(255,255,255,.04);border:1px solid var(--hair);
  color:var(--paper);font-family:var(--mono);font-size:11px;padding:8px;border-radius:2px}
.request-builder__line input{flex:1;background:rgba(255,255,255,.04);border:1px solid var(--hair);
  color:var(--paper);font-family:var(--mono);font-size:11px;padding:8px;border-radius:2px}
.request-builder__headers,.request-builder__body{background:rgba(255,255,255,.03);border:1px solid var(--hair);
  color:var(--paper);font-family:var(--mono);font-size:11px;padding:8px;border-radius:2px;
  min-height:44px;resize:vertical}
.dive__history{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:4px}
.dive__history li{font-family:var(--mono);font-size:11px;padding:4px 8px;border-radius:2px}
```

- [ ] **Step 6: Write a pure-logic test for `guessUrl`/`guessBody`**

`RequestBuilder.tsx` mixes stateful JSX with two pure helper functions
(`guessUrl`, `guessBody`). Following this codebase's own established
pattern (`nodeLabel.ts` was extracted specifically so pure logic could be
tested without a DOM — no `@testing-library` dependency exists in this
project), export both functions from `RequestBuilder.tsx` and test them
directly.

In `RequestBuilder.tsx`, change:

```typescript
function guessUrl(workspace: Workspace, node: Node): string {
```

to:

```typescript
export function guessUrl(workspace: Workspace, node: Node): string {
```

and:

```typescript
function guessBody(node: Node): string {
```

to:

```typescript
export function guessBody(node: Node): string {
```

Create `frontend/src/components/RequestBuilder.test.ts`:

```typescript
import { describe, expect, it } from 'vitest'
import type { Node, Workspace } from '../api'
import { guessBody, guessUrl } from './RequestBuilder'

const baseWorkspace: Workspace = {
  id: 'w1', name: 'Test', schema_kind: 'openapi', base_path: '/api/v3',
  schema_source: 'https://petstore3.swagger.io/api/v3/openapi.json',
  nodes: [], edges: [],
}

const restNode: Node = {
  id: 'n1', kind: 'rest_operation', method: 'GET', path_template: '/pet/{petId}',
  operation_id: 'getPetById', type_name: null, field_name: null,
  declared_request_schema: null, declared_response_schema: null, call_count: 0,
}

const graphqlNode: Node = {
  id: 'n2', kind: 'graphql_field', method: null, path_template: null,
  operation_id: null, type_name: 'Query', field_name: 'pet',
  declared_request_schema: null, declared_response_schema: null, call_count: 0,
}

const mutationNode: Node = { ...graphqlNode, id: 'n3', type_name: 'Mutation', field_name: 'addPet' }

describe('guessUrl', () => {
  it('builds a real REST URL from origin + base_path + path_template', () => {
    expect(guessUrl(baseWorkspace, restNode)).toBe('https://petstore3.swagger.io/api/v3/pet/{petId}')
  })

  it('uses schema_source directly for a GraphQL node', () => {
    const ws: Workspace = { ...baseWorkspace, schema_kind: 'graphql', schema_source: 'https://countries.trevorblades.com/graphql' }
    expect(guessUrl(ws, graphqlNode)).toBe('https://countries.trevorblades.com/graphql')
  })

  it('returns empty string for a pasted schema (no real URL to guess from)', () => {
    const ws: Workspace = { ...baseWorkspace, schema_source: 'pasted' }
    expect(guessUrl(ws, restNode)).toBe('')
  })
})

describe('guessBody', () => {
  it('returns empty string for a REST node', () => {
    expect(guessBody(restNode)).toBe('')
  })

  it('builds a shorthand query skeleton for a Query field', () => {
    expect(guessBody(graphqlNode)).toBe(JSON.stringify({ query: '{ pet }' }, null, 2))
  })

  it('builds an explicit mutation skeleton for a Mutation field', () => {
    expect(guessBody(mutationNode)).toBe(JSON.stringify({ query: 'mutation { addPet }' }, null, 2))
  })
})
```

- [ ] **Step 7: Run the checks**

Run: `cd frontend && npx vitest run`
Expected: 13 passed (7 prior + 6 new).

Run: `cd frontend && npx tsc -b`
Expected: no errors.

Run: `cd frontend && npx vite build`
Expected: succeeds (expected chunk-size warning only).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api.ts frontend/src/components/RequestBuilder.tsx frontend/src/components/RequestBuilder.test.ts \
        frontend/src/components/DetailPanel.tsx frontend/src/App.tsx frontend/src/styles.css
git commit -m "feat: real request-builder UI with curl-paste + node history (replaces the broken Send button)"
```

---

### Task 3: Workspace-wide history view (frontend)

**Files:**
- Create: `frontend/src/components/HistoryPanel.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: `getWorkspaceRequests(workspaceId): Promise<RequestHistoryEntry[]>` (Task 2, already in `api.ts`).
- Produces: `<HistoryPanel workspace={Workspace} onClose={() => void} />` — a toggleable panel listing every real request sent in the workspace, filterable by node (SPEC.md §8.4).

- [ ] **Step 1: Create `components/HistoryPanel.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { getWorkspaceRequests, type RequestHistoryEntry, type Workspace } from '../api'
import { nodeLabel } from '../lib/nodeLabel'

export function HistoryPanel({ workspace, onClose }: { workspace: Workspace; onClose: () => void }) {
  const [requests, setRequests] = useState<RequestHistoryEntry[]>([])
  const [filterNodeId, setFilterNodeId] = useState('')

  useEffect(() => {
    getWorkspaceRequests(workspace.id).then(setRequests).catch(() => setRequests([]))
  }, [workspace.id])

  const nodeLabelById = new Map(workspace.nodes.map((n) => [n.id, nodeLabel(n).title]))
  const matchedNodeIds = [...new Set(requests.map((r) => r.node_id).filter((id): id is string => id !== null))]
  const filtered = filterNodeId ? requests.filter((r) => r.node_id === filterNodeId) : requests

  return (
    <div className="history-backdrop" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="history-panel" role="dialog" aria-modal="true" aria-label="Request history">
        <button type="button" className="dive__close" onClick={onClose} aria-label="Close history">Close ✕</button>
        <h3 className="dive__title">History</h3>
        <select
          className="history-panel__filter" value={filterNodeId}
          onChange={(e) => setFilterNodeId(e.target.value)} aria-label="Filter by node"
        >
          <option value="">All nodes</option>
          {matchedNodeIds.map((id) => (
            <option key={id} value={id}>{nodeLabelById.get(id) ?? id}</option>
          ))}
        </select>
        <ul className="history-panel__list">
          {filtered.map((r) => (
            <li key={r.id}>
              <span className="dive__label">{r.method}</span> {r.url}
              <span className="dive__detail"> — {new Date(r.sent_at).toLocaleString()}</span>
            </li>
          ))}
          {filtered.length === 0 && <li className="dive__detail">No requests sent yet.</li>}
        </ul>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Wire it into `App.tsx`**

Add the import:

```typescript
import { HistoryPanel } from './components/HistoryPanel'
```

Add state alongside the existing ones:

```typescript
  const [showHistory, setShowHistory] = useState(false)
```

In the JSX, inside `.hud-top`, add a History button right after `<WorkspaceList .../>` and before `<WorkspaceForm .../>` — but only when a workspace is loaded:

```tsx
          {workspace && (
            <button type="button" className="history-toggle" onClick={() => setShowHistory(true)}>
              History
            </button>
          )}
```

Right after the closing `</div>` of `.scene-root` (i.e. as a sibling of `.scene-root`, alongside `<DetailPanel .../>`), add:

```tsx
      {workspace && showHistory && (
        <HistoryPanel workspace={workspace} onClose={() => setShowHistory(false)} />
      )}
```

- [ ] **Step 3: Style the toggle button and panel**

Append to `frontend/src/styles.css`:

```css
.history-toggle{background:transparent;border:1px solid var(--hair);color:var(--mute);
  font-family:var(--mono);font-size:10px;padding:9px 16px;border-radius:2px;cursor:pointer;margin-left:16px}
.history-toggle:hover{border-color:var(--match);color:var(--match)}
.history-backdrop{position:fixed;inset:0;z-index:25;background:rgba(0,0,0,.5);
  display:flex;align-items:center;justify-content:center}
.history-panel{width:min(560px,92vw);max-height:80vh;overflow-y:auto;background:#0A0C14;
  border:1px solid var(--hair);border-radius:4px;padding:28px;position:relative}
.history-panel__filter{background:rgba(255,255,255,.04);border:1px solid var(--hair);
  color:var(--paper);font-family:var(--mono);font-size:11px;padding:8px;border-radius:2px;
  margin-bottom:14px}
.history-panel__list{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:8px}
.history-panel__list li{font-family:var(--mono);font-size:11px;padding:8px;
  border:1px solid var(--hair);border-radius:2px;word-break:break-all}
```

- [ ] **Step 4: Run the checks**

Run: `cd frontend && npx vitest run`
Expected: 13 passed (unchanged — no new test files this task, matching the codebase's existing precedent of no direct tests for stateful/effectful components).

Run: `cd frontend && npx tsc -b`
Expected: no errors.

Run: `cd frontend && npx vite build`
Expected: succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/HistoryPanel.tsx frontend/src/App.tsx frontend/src/styles.css
git commit -m "feat: workspace-wide history view (SPEC.md §8.4)"
```

---

### Task 4: Live verification + `HANDOFF.md`

**Files:**
- Modify: `HANDOFF.md`

**Interfaces:**
- Consumes: Tasks 1-3's complete, committed changes. No new interfaces — this task verifies and documents.

- [ ] **Step 1: Start the real stack**

```bash
cd backend
docker compose up -d
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/alembic upgrade head
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/uvicorn app.main:app --port 8123 &
cd ../frontend && npm run dev &
```

- [ ] **Step 2: Live-verify in a real browser — this is the first phase where the whole pipeline is browser-drivable end to end**

Open the app (`http://localhost:5173`).

**REST flow:**
- Create a workspace with `https://petstore3.swagger.io/api/v3/openapi.json`.
- Click a node (e.g. the one for `GET /pet/{petId}`). Confirm the detail panel shows the real request-builder with a pre-filled method (`GET`) and a real, correct pre-filled URL (`https://petstore3.swagger.io/api/v3/pet/{petId}` — note the literal `{petId}` the user needs to fill in, a real known limitation, not a bug).
- Edit the URL to a real pet id (e.g. replace `{petId}` with `1`). Click Send. Confirm a real response comes back with a real drift status, and the node's color updates in the 3D graph.
- Paste a real curl command (e.g. `curl -X GET 'https://petstore3.swagger.io/api/v3/pet/findByStatus?status=available'`) into the curl box, click "Parse curl", confirm the method/url fields update, click Send, confirm a real result comes back.
- Open the workspace-wide History panel (the new "History" button). Confirm it lists the real requests just sent, with real timestamps. Confirm the node filter dropdown works.

**GraphQL flow:**
- Create a second workspace with `https://countries.trevorblades.com/graphql`.
- Click a node (e.g. `country`). Confirm the pre-filled body is a real, valid GraphQL query skeleton (`{"query": "{ country }"}` — note this is missing the required `code` argument, a real known limitation the user must fill in, matching this plan's stated v1 matching/pre-fill scope).
- Edit the body to a real, complete query (e.g. `{"query": "{ country(code: \"US\") { name } }"}`), confirm the method defaults to `POST` and the URL is pre-filled with the real GraphQL endpoint. Click Send. Confirm a real response comes back, a real node match, and a real drift status.

Also re-confirm the SSRF guard still holds through this new UI path (not just via curl, per Phase 2a): attempt a Send with the URL manually edited to `http://169.254.169.254/`, confirm the backend rejects it (502) and the UI surfaces the error, not a crash.

- [ ] **Step 3: Update `HANDOFF.md`**

Append a new `## Phase 2b: GraphQL Drift-Checking + Real Request-Builder UI`
section (after the Phase 2a section), following that section's own
structure. It must state plainly:
- GraphQL request-matching + drift-checking now real (SPEC.md Phase 2
  is complete for both protocols), with its stated v1 scope boundaries
  (first-operation/first-field matching, scalar-precise but
  object-shallow drift-checking) named explicitly, not implied as more
  than they are.
- The frontend's Send button is no longer honestly broken — the real
  request-builder + curl-paste + history UI, live-verified end to end
  in a real browser against both a real REST API (Petstore) and a real
  GraphQL API (countries.trevorblades.com), including a real SSRF
  rejection surfacing correctly in the UI.
- The real test counts (confirm the actual final numbers from Task 1's
  Step 8 `pytest -q` output and Task 2's Step 7 `vitest run` output).
- Still-open, explicitly named gaps carried forward or newly identified:
  GraphQL's dual-mode 3D graph layout (SPEC.md §8.3 — type-relationship
  graph with Query/Mutation as roots — GraphQL nodes still render with
  no edges, a gap named since Phase 1c); host-blind REST request
  matching (Phase 2a's deferred finding, still not fixed); real GitHub
  OAuth accounts and per-user credential storage (SPEC.md Phase 3,
  never attempted); the shared-executor timeout queue-wait edge case
  under high concurrency (Phase 2a's parked finding).
- Next: Phase 3 (SPEC.md §10) — real GitHub OAuth, workspaces scoped
  per user, encrypted credential storage, the final visual-identity
  palette/type pass, deploy to Render.

- [ ] **Step 4: Commit**

```bash
git add HANDOFF.md
git commit -m "docs: Phase 2b HANDOFF — GraphQL drift-checking + request-builder UI, live-verified"
```
