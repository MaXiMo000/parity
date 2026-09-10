# Phase 0 Walking Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the 3D rendering, styling, and click-to-detail-to-send
interaction loop actually work end to end, against a hand-written fixture
workspace, before any real OpenAPI/GraphQL parsing or real request
proxying exists.

**Architecture:** A minimal FastAPI backend serves one hand-written fixture
workspace (5 REST-operation nodes shaped like a small task-manager API)
over the real Phase-1 route shapes, with no database yet — the fixture
lives in a Python module. A "send request" route returns a canned,
deterministic fake result per node (4 `matched`, 1 `violated`) rather than
proxying anywhere real. A Vite + React + TypeScript + React Three Fiber
frontend fetches that workspace, renders it as a real 3D graph (nodes
grouped by shared path via `d3-force-3d`, camera auto-fit via
`@react-three/drei`'s `Bounds`), and wires up click → detail panel → Send
→ the node's color updates from the real (fake) response.

**Tech Stack:** FastAPI, pytest; Vite, React, TypeScript, React Three
Fiber, `@react-three/drei`, `@react-three/postprocessing`, `d3-force-3d`,
Vitest.

**Spec:** `SPEC.md` (repo root) — this plan implements §10 Phase 0
specifically; §7.5/§7.6 define the *real* v1 data model and routes this
phase's shapes are a genuine (not fake-shaped) subset of, so nothing here
needs to change shape once Phase 1 makes it real.

## Global Constraints

- No imported/modeled 3D assets — every node/edge is a procedural
  primitive built in code (SPEC.md §8.2).
- New, standalone visual identity — not the portfolio's or `loom`'s
  palette/type tokens (SPEC.md §8.2, §13). This plan fixes the exact
  values (below) as the real Phase 0 decision that section deferred.
- Node/edge/workspace field names here must match SPEC.md §7.5's real
  column names exactly (`path_template`, `operation_id`,
  `declared_request_schema`, `declared_response_schema`, `call_count`,
  drift status values `matched`/`violated`/`unverified_no_schema`/
  `unverified_no_match`) — Phase 1 adds Postgres under the same shape,
  it must not need to rename anything Phase 0 already shipped.
- Git identity: before the first commit, `git config user.email` in this
  repo must already be `109451965+MaXiMo000@users.noreply.github.com`
  (already set — confirm, don't re-set blindly).

**Visual identity fixed for this plan** (SPEC.md §13's deferred decision):

```css
--ink:#05060B;        /* base background */
--paper:#E9ECF4;       /* primary text */
--mute:#7C879C;        /* secondary text/borders */
--hair:rgba(255,255,255,.08);
--match:#4ADE80;       /* matched/verified */
--violate:#FB4570;     /* violated */
--disp:"Space Grotesk", system-ui, sans-serif;   /* display/UI */
--mono:"IBM Plex Mono", ui-monospace, Menlo, monospace; /* technical values */
```

Loaded via Google Fonts CDN link in `index.html` (not self-hosted —
`loom`'s self-hosting was specifically to match the portfolio family's
own discipline; parity is standalone and has no such requirement. Add
self-hosting later if a real perf/privacy reason shows up).

---

### Task 1: Backend scaffold + fixture data

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/fixtures.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_fixtures.py`

**Interfaces:**
- Produces: `app.fixtures.FIXTURE_WORKSPACE_ID: str`,
  `app.fixtures.fixture_workspace() -> dict` (shape: `{id, name,
  schema_kind, nodes: [dict, ...]}`, each node dict:
  `{id, kind, method, path_template, operation_id,
  declared_request_schema, declared_response_schema, call_count}`),
  `app.fixtures.fixture_edges() -> list[tuple[str, str]]` (pairs of node
  ids sharing a path template).
- Produces: `app.main.app` (a FastAPI instance, no routes yet — Task 2
  adds them).

- [ ] **Step 1: Write `backend/pyproject.toml`**

```toml
[project]
name = "parity-backend"
version = "0.1.0"
description = "parity backend — Phase 0: fixture workspace only"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "httpx>=0.27",
]

[tool.setuptools.packages.find]
include = ["app*"]
```

- [ ] **Step 2: Create empty `backend/app/__init__.py` and `backend/tests/__init__.py`**

- [ ] **Step 3: Write the failing test `backend/tests/test_fixtures.py`**

```python
from app.fixtures import FIXTURE_WORKSPACE_ID, fixture_edges, fixture_workspace


def test_fixture_workspace_shape():
    ws = fixture_workspace()
    assert ws["id"] == FIXTURE_WORKSPACE_ID
    assert ws["schema_kind"] == "openapi"
    assert len(ws["nodes"]) == 5

    by_op = {n["operation_id"]: n for n in ws["nodes"]}
    assert set(by_op) == {
        "list_tasks", "create_task", "get_task", "update_task", "delete_task",
    }
    assert by_op["list_tasks"]["method"] == "GET"
    assert by_op["list_tasks"]["path_template"] == "/tasks"
    assert by_op["get_task"]["path_template"] == "/tasks/{id}"
    # every node has both schema fields present (even if null), matching
    # SPEC.md §7.5's real column set — Phase 1 populates these for real,
    # Phase 0 must already carry the same keys.
    for n in ws["nodes"]:
        assert "declared_request_schema" in n
        assert "declared_response_schema" in n
        assert n["call_count"] == 0


def test_fixture_edges_only_reference_real_nodes():
    ws = fixture_workspace()
    node_ids = {n["id"] for n in ws["nodes"]}
    edges = fixture_edges()
    assert len(edges) == 3
    for a, b in edges:
        assert a in node_ids
        assert b in node_ids
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]" && .venv/bin/python -m pytest tests/test_fixtures.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.fixtures'`

- [ ] **Step 5: Write `backend/app/fixtures.py`**

```python
"""Phase 0 walking-skeleton data: one hand-written, realistic-shaped
REST API (a small task manager) — no real OpenAPI parsing yet (Phase 1),
no real request proxying yet (Phase 2). Field names match SPEC.md §7.5's
real `node` columns exactly, so nothing here needs to change shape once
Phase 1 makes it real.
"""
from __future__ import annotations

from typing import Any

FIXTURE_WORKSPACE_ID = "phase0-fixture-workspace"

_TASK_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "title": {"type": "string"},
        "done": {"type": "boolean"},
    },
    "required": ["id", "title", "done"],
}

_NODES: list[dict[str, Any]] = [
    dict(
        id="list_tasks", kind="rest_operation", method="GET", path_template="/tasks",
        operation_id="list_tasks", declared_request_schema=None,
        declared_response_schema={"type": "array", "items": _TASK_ITEM_SCHEMA},
        call_count=0,
    ),
    dict(
        id="create_task", kind="rest_operation", method="POST", path_template="/tasks",
        operation_id="create_task",
        declared_request_schema={
            "type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"],
        },
        declared_response_schema=_TASK_ITEM_SCHEMA,
        call_count=0,
    ),
    dict(
        id="get_task", kind="rest_operation", method="GET", path_template="/tasks/{id}",
        operation_id="get_task", declared_request_schema=None,
        declared_response_schema=_TASK_ITEM_SCHEMA,
        call_count=0,
    ),
    dict(
        id="update_task", kind="rest_operation", method="PATCH", path_template="/tasks/{id}",
        operation_id="update_task",
        declared_request_schema={
            "type": "object", "properties": {"title": {"type": "string"}, "done": {"type": "boolean"}},
        },
        declared_response_schema=_TASK_ITEM_SCHEMA,
        call_count=0,
    ),
    dict(
        id="delete_task", kind="rest_operation", method="DELETE", path_template="/tasks/{id}",
        operation_id="delete_task", declared_request_schema=None,
        declared_response_schema=None,
        call_count=0,
    ),
]

# Pairs of node ids that share a path template — the frontend renders an
# edge per pair so the 3D layout clusters an endpoint's methods together.
# Real Phase-1 grouping (by tag/path hierarchy) replaces this; Phase 0
# just needs *a* real, non-arbitrary grouping rule.
_EDGES: list[tuple[str, str]] = [
    ("list_tasks", "create_task"),
    ("get_task", "update_task"),
    ("update_task", "delete_task"),
]


def fixture_workspace() -> dict[str, Any]:
    return {
        "id": FIXTURE_WORKSPACE_ID,
        "name": "Task Manager (fixture)",
        "schema_kind": "openapi",
        "nodes": [dict(n) for n in _NODES],
    }


def fixture_edges() -> list[tuple[str, str]]:
    return list(_EDGES)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_fixtures.py -v`
Expected: PASS (2 passed)

- [ ] **Step 7: Write `backend/app/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="parity", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 8: Live-verify the server actually starts**

Run: `cd backend && .venv/bin/uvicorn app.main:app --port 8123 &`
then `sleep 1 && curl -s http://127.0.0.1:8123/health && kill %1`
Expected: `{"status":"ok"}`

- [ ] **Step 9: Commit**

```bash
cd backend && git add pyproject.toml app/ tests/
git commit -m "backend: fixture workspace data + bare FastAPI app"
```

---

### Task 2: Workspace routes

**Files:**
- Create: `backend/app/routes/__init__.py`
- Create: `backend/app/routes/workspaces.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_workspace_routes.py`

**Interfaces:**
- Consumes: `app.fixtures.fixture_workspace()`, `app.fixtures.fixture_edges()`, `app.fixtures.FIXTURE_WORKSPACE_ID` (Task 1).
- Produces: `app.routes.workspaces.router` (a FastAPI `APIRouter`), mounted
  at prefix `/api/workspaces`. Response shape for `GET /api/workspaces/{id}`
  adds `"edges": [{"from_node": str, "to_node": str}, ...]` alongside the
  workspace dict's existing keys — this is the shape Task 5 (frontend)
  consumes.

- [ ] **Step 1: Write the failing test `backend/tests/test_workspace_routes.py`**

```python
from fastapi.testclient import TestClient

from app.fixtures import FIXTURE_WORKSPACE_ID
from app.main import app

client = TestClient(app)


def test_list_workspaces_returns_the_fixture():
    r = client.get("/api/workspaces")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["id"] == FIXTURE_WORKSPACE_ID
    assert body[0]["schema_kind"] == "openapi"


def test_get_workspace_includes_nodes_and_edges():
    r = client.get(f"/api/workspaces/{FIXTURE_WORKSPACE_ID}")
    assert r.status_code == 200
    body = r.json()
    assert len(body["nodes"]) == 5
    assert len(body["edges"]) == 3
    node_ids = {n["id"] for n in body["nodes"]}
    for e in body["edges"]:
        assert e["from_node"] in node_ids
        assert e["to_node"] in node_ids


def test_get_unknown_workspace_is_404():
    r = client.get("/api/workspaces/not-a-real-id")
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_workspace_routes.py -v`
Expected: FAIL — 404 on `/api/workspaces` (no such route registered)

- [ ] **Step 3: Create empty `backend/app/routes/__init__.py`**

- [ ] **Step 4: Write `backend/app/routes/workspaces.py`**

```python
"""GET /api/workspaces and GET /api/workspaces/{id} — Phase 0 serves only
the one fixture workspace (app/fixtures.py). Real workspace CRUD against
Postgres is Phase 1 (SPEC.md §10); this route's response shape is already
the real Phase-1 shape."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.fixtures import FIXTURE_WORKSPACE_ID, fixture_edges, fixture_workspace

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.get("")
def list_workspaces() -> list[dict]:
    ws = fixture_workspace()
    return [{"id": ws["id"], "name": ws["name"], "schema_kind": ws["schema_kind"]}]


@router.get("/{workspace_id}")
def get_workspace(workspace_id: str) -> dict:
    if workspace_id != FIXTURE_WORKSPACE_ID:
        raise HTTPException(status_code=404, detail="unknown workspace id (Phase 0 only serves the fixture)")
    ws = fixture_workspace()
    ws["edges"] = [{"from_node": a, "to_node": b} for a, b in fixture_edges()]
    return ws
```

- [ ] **Step 5: Wire the router into `backend/app/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.workspaces import router as workspaces_router

app = FastAPI(title="parity", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(workspaces_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 6: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: PASS (5 passed)

- [ ] **Step 7: Commit**

```bash
git add app/routes/ app/main.py tests/test_workspace_routes.py
git commit -m "backend: GET /api/workspaces and GET /api/workspaces/{id}"
```

---

### Task 3: Fake "send request" route

**Files:**
- Create: `backend/app/routes/requests.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_request_routes.py`

**Interfaces:**
- Consumes: `app.fixtures.fixture_workspace()`, `FIXTURE_WORKSPACE_ID`.
- Produces: `app.routes.requests.router`, `POST
  /api/workspaces/{workspace_id}/requests` accepting
  `{"node_id": str}` and returning `{"request": {...}, "response":
  {"status_code": int, "body": Any}, "drift_finding": {"status": "matched"
  | "violated", "detail": str}}` — the exact response shape Task 7
  (frontend Send interaction) consumes.

- [ ] **Step 1: Write the failing test `backend/tests/test_request_routes.py`**

```python
from fastapi.testclient import TestClient

from app.fixtures import FIXTURE_WORKSPACE_ID
from app.main import app

client = TestClient(app)


def test_send_matched_node():
    r = client.post(f"/api/workspaces/{FIXTURE_WORKSPACE_ID}/requests", json={"node_id": "get_task"})
    assert r.status_code == 200
    body = r.json()
    assert body["drift_finding"]["status"] == "matched"
    assert body["response"]["status_code"] == 200
    assert body["response"]["body"]["id"] == "t1"


def test_send_violated_node():
    # create_task's canned response is deliberately missing the required
    # "done" field its own declared_response_schema requires.
    r = client.post(f"/api/workspaces/{FIXTURE_WORKSPACE_ID}/requests", json={"node_id": "create_task"})
    assert r.status_code == 200
    body = r.json()
    assert body["drift_finding"]["status"] == "violated"
    assert "done" in body["drift_finding"]["detail"]
    assert "done" not in body["response"]["body"]


def test_send_unknown_node_is_404():
    r = client.post(f"/api/workspaces/{FIXTURE_WORKSPACE_ID}/requests", json={"node_id": "not-a-real-node"})
    assert r.status_code == 404


def test_send_unknown_workspace_is_404():
    r = client.post("/api/workspaces/not-real/requests", json={"node_id": "get_task"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_request_routes.py -v`
Expected: FAIL — 404 (no such route)

- [ ] **Step 3: Write `backend/app/routes/requests.py`**

```python
"""POST /api/workspaces/{id}/requests — Phase 0: a canned, deterministic
fake result per fixture node, never a real proxy call. Real request
execution against the real target server, real curl parsing, and real
schema validation are Phase 2 (SPEC.md §10, §7.3's SSRF-guarded proxy).
This route's response shape is already the real Phase-2 shape, so the
frontend built against it today doesn't change later.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.fixtures import FIXTURE_WORKSPACE_ID, fixture_workspace

router = APIRouter(prefix="/api/workspaces", tags=["requests"])

# One canned (request, response, drift_finding) per fixture node id.
# create_task's response is deliberately missing "done" -- the one
# violated node the fixture is built to demonstrate (matches SPEC.md's
# own "mostly clean, one real finding" fixture discipline, see loom's
# own fixture for the precedent).
_CANNED: dict[str, dict[str, Any]] = {
    "list_tasks": {
        "response": {"status_code": 200, "body": [{"id": "t1", "title": "Write SPEC", "done": True}]},
        "drift_finding": {"status": "matched", "detail": "response matches the declared array-of-task schema"},
    },
    "create_task": {
        "response": {"status_code": 201, "body": {"id": "t2", "title": "Ship Phase 0"}},
        "drift_finding": {
            "status": "violated",
            "detail": "response is missing required field 'done' declared in the response schema",
        },
    },
    "get_task": {
        "response": {"status_code": 200, "body": {"id": "t1", "title": "Write SPEC", "done": True}},
        "drift_finding": {"status": "matched", "detail": "response matches the declared task schema"},
    },
    "update_task": {
        "response": {"status_code": 200, "body": {"id": "t1", "title": "Write SPEC", "done": False}},
        "drift_finding": {"status": "matched", "detail": "response matches the declared task schema"},
    },
    "delete_task": {
        "response": {"status_code": 204, "body": None},
        "drift_finding": {"status": "matched", "detail": "204 with no body, as declared"},
    },
}


@router.post("/{workspace_id}/requests")
def send_request(workspace_id: str, body: dict) -> dict:
    if workspace_id != FIXTURE_WORKSPACE_ID:
        raise HTTPException(status_code=404, detail="unknown workspace id")
    node_id = body.get("node_id")
    canned = _CANNED.get(node_id)
    if canned is None:
        raise HTTPException(status_code=404, detail="unknown node id")

    node = next(n for n in fixture_workspace()["nodes"] if n["id"] == node_id)
    return {
        "request": {"node_id": node_id, "method": node["method"], "url": f"https://example.invalid{node['path_template']}"},
        "response": canned["response"],
        "drift_finding": canned["drift_finding"],
    }
```

- [ ] **Step 4: Wire the router into `backend/app/main.py`**

Add `from app.routes.requests import router as requests_router` and
`app.include_router(requests_router)` alongside the existing
`workspaces_router` include.

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: PASS (9 passed)

- [ ] **Step 6: Commit**

```bash
git add app/routes/requests.py app/main.py tests/test_request_routes.py
git commit -m "backend: fake POST /api/workspaces/{id}/requests"
```

---

### Task 4: Frontend scaffold, design tokens, typed API client

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`, `frontend/tsconfig.app.json`, `frontend/tsconfig.node.json`
- Create: `frontend/index.html`
- Create: `frontend/src/styles.css`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx` (minimal placeholder — Task 5/6/7 build it out)

**Interfaces:**
- Produces (`api.ts`): `export interface Node {...}`, `export interface
  Workspace {...}`, `export interface SendResult {...}`,
  `getWorkspace(id: string): Promise<Workspace>`,
  `sendRequest(workspaceId: string, nodeId: string): Promise<SendResult>`.
  These exact names/shapes are what Tasks 5-7 import.

- [ ] **Step 1: Write `frontend/package.json`**

```json
{
  "name": "parity-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "@react-three/drei": "^10.7.8",
    "@react-three/fiber": "^9.7.0",
    "@react-three/postprocessing": "^3.0.5",
    "d3-force-3d": "^3.0.5",
    "react": "19.2.8",
    "react-dom": "19.2.8",
    "three": "^0.185.1"
  },
  "devDependencies": {
    "@types/node": "^22.20.2",
    "@types/react": "^19.2.17",
    "@types/react-dom": "^19.2.3",
    "@types/three": "^0.185.0",
    "@vitejs/plugin-react": "^6.0.4",
    "typescript": "~6.0.2",
    "vite": "^8.2.0",
    "vitest": "^3.2.4"
  }
}
```

- [ ] **Step 2: Write `frontend/vite.config.ts`**

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8123',
    },
  },
})
```

- [ ] **Step 3: Write `frontend/tsconfig.json`**

```json
{
  "files": [],
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" }
  ]
}
```

- [ ] **Step 4: Write `frontend/tsconfig.app.json`**

```json
{
  "compilerOptions": {
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.app.tsbuildinfo",
    "target": "es2023",
    "lib": ["ES2023", "DOM"],
    "module": "esnext",
    "types": ["vite/client"],
    "allowArbitraryExtensions": true,
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "verbatimModuleSyntax": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "erasableSyntaxOnly": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
```

- [ ] **Step 5: Write `frontend/tsconfig.node.json`**

```json
{
  "compilerOptions": {
    "tsBuildInfoFile": "./node_modules/.tmp/tsconfig.node.tsbuildinfo",
    "target": "es2023",
    "lib": ["ES2023"],
    "module": "esnext",
    "types": ["node"],
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "verbatimModuleSyntax": true,
    "moduleDetection": "force",
    "noEmit": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 6: Write `frontend/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Space+Grotesk:wght@400;500;700&display=swap" rel="stylesheet">
    <title>parity</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 7: Write `frontend/src/styles.css`**

```css
/* Standalone design tokens (SPEC.md §8.2, §13's deferred decision, fixed
   in docs/superpowers/plans/2026-09-10-phase0-walking-skeleton.md's
   Global Constraints). Not the portfolio's or loom's palette. */
:root{
  --ink:#05060B; --paper:#E9ECF4; --mute:#7C879C; --hair:rgba(255,255,255,.08);
  --match:#4ADE80; --violate:#FB4570;
  --disp:"Space Grotesk",system-ui,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body,#root{height:100%}
body{background:var(--ink);color:var(--paper);font-family:var(--disp);
  -webkit-font-smoothing:antialiased;overflow:hidden}
a:focus-visible,[href]:focus-visible,button:focus-visible,input:focus-visible{
  outline:2px solid var(--match);outline-offset:2px}

.app{position:relative;width:100vw;height:100vh}
canvas{display:block}

.hud-top{position:fixed;top:0;left:0;right:0;z-index:5;display:flex;
  align-items:center;gap:16px;padding:22px 28px;pointer-events:none}
.hud-top > *{pointer-events:auto}
.brand{font-size:14px;letter-spacing:.08em;text-transform:uppercase;font-weight:700}
.brand span{color:var(--match)}
```

- [ ] **Step 8: Write `frontend/src/api.ts`**

```ts
export interface Node {
  id: string
  kind: 'rest_operation'
  method: string
  path_template: string
  operation_id: string
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
  schema_kind: 'openapi'
  nodes: Node[]
  edges: Edge[]
}

export interface WorkspaceSummary {
  id: string
  name: string
  schema_kind: Workspace['schema_kind']
}

export interface SendResult {
  request: { node_id: string; method: string; url: string }
  response: { status_code: number; body: unknown }
  drift_finding: { status: 'matched' | 'violated'; detail: string }
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status} ${detail}`)
  }
  return res.json() as Promise<T>
}

export function listWorkspaces(): Promise<WorkspaceSummary[]> {
  return fetch('/api/workspaces').then((res) => json<WorkspaceSummary[]>(res))
}

export function getWorkspace(id: string): Promise<Workspace> {
  return fetch(`/api/workspaces/${encodeURIComponent(id)}`).then((res) => json<Workspace>(res))
}

export function sendRequest(workspaceId: string, nodeId: string): Promise<SendResult> {
  return fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/requests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ node_id: nodeId }),
  }).then((res) => json<SendResult>(res))
}
```

- [ ] **Step 9: Write a minimal placeholder `frontend/src/App.tsx`**

```tsx
export function App() {
  return (
    <div className="app">
      <div className="hud-top">
        <div className="brand">parity<span>.</span></div>
      </div>
    </div>
  )
}
```

- [ ] **Step 10: Write `frontend/src/main.tsx`**

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

- [ ] **Step 11: Install and verify it builds**

Run: `cd frontend && npm install && npx tsc -b && npx vite build`
Expected: clean typecheck, a successful build with no errors.

- [ ] **Step 12: Commit**

```bash
git add package.json vite.config.ts tsconfig*.json index.html src/
git commit -m "frontend: scaffold, design tokens, typed API client"
```

---

### Task 5: 3D graph rendering

**Files:**
- Create: `frontend/src/scene/layout.ts`
- Create: `frontend/src/scene/Node.tsx`
- Create: `frontend/src/scene/Edge.tsx`
- Create: `frontend/src/scene/Graph.tsx`
- Create: `frontend/src/lib/severity.ts`
- Create: `frontend/src/lib/severity.test.ts`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `Node`, `Edge`, `Workspace` from `api.ts` (Task 4).
- Produces (`severity.ts`): `export function nodeColor(status:
  'unverified' | 'matched' | 'violated'): { color: string;
  emissiveIntensity: number }` — Task 6/7 read this too.
- Produces (`layout.ts`): `export interface LaidOutNode extends Node { x:
  number; y: number; z: number; status: 'unverified' | 'matched' |
  'violated' }`, `export function computeLayout(nodes: Node[], edges:
  Edge[]): Map<string, LaidOutNode>`.
- Produces (`Graph.tsx`): `<Graph nodes edges statuses onSelect />` where
  `statuses: Record<string, 'unverified'|'matched'|'violated'>` and
  `onSelect: (id: string) => void`.

- [ ] **Step 1: Write the failing test `frontend/src/lib/severity.test.ts`**

```ts
import { describe, expect, it } from 'vitest'
import { COLOR, nodeColor } from './severity'

describe('nodeColor', () => {
  it('matched reads the match color', () => {
    expect(nodeColor('matched').color).toBe(COLOR.match)
  })
  it('violated reads the violate color', () => {
    expect(nodeColor('violated').color).toBe(COLOR.violate)
  })
  it('unverified reads neutral, dim', () => {
    const c = nodeColor('unverified')
    expect(c.color).toBe(COLOR.neutral)
    expect(c.emissiveIntensity).toBeLessThan(0.3)
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run`
Expected: FAIL — cannot find module `./severity`

- [ ] **Step 3: Write `frontend/src/lib/severity.ts`**

```ts
export type DriftStatus = 'unverified' | 'matched' | 'violated'

export const COLOR = {
  match: '#4ADE80',
  violate: '#FB4570',
  neutral: '#7C879C',
} as const

export function nodeColor(status: DriftStatus): { color: string; emissiveIntensity: number } {
  switch (status) {
    case 'matched':
      return { color: COLOR.match, emissiveIntensity: 1.0 }
    case 'violated':
      return { color: COLOR.violate, emissiveIntensity: 1.3 }
    default:
      return { color: COLOR.neutral, emissiveIntensity: 0.12 }
  }
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npx vitest run`
Expected: PASS (3 passed)

- [ ] **Step 5: Write `frontend/src/scene/layout.ts`**

```ts
// @ts-expect-error — d3-force-3d ships no published types.
import { forceCenter, forceLink, forceManyBody, forceSimulation, forceX, forceY, forceZ } from 'd3-force-3d'
import type { Edge, Node } from '../api'
import type { DriftStatus } from '../lib/severity'

export interface LaidOutNode extends Node {
  x: number
  y: number
  z: number
  status: DriftStatus
}

const SETTLE_TICKS = 300

export function computeLayout(
  nodes: Node[],
  edges: Edge[],
  statuses: Record<string, DriftStatus>,
): Map<string, LaidOutNode> {
  const simNodes = nodes.map((n) => ({ ...n }))
  const simLinks = edges.map((e) => ({ source: e.from_node, target: e.to_node }))

  const sim = forceSimulation(simNodes, 3)
    .force('link', forceLink(simLinks).id((d: { id: string }) => d.id).distance(2.2))
    .force('charge', forceManyBody().strength(-6))
    .force('center', forceCenter())
    .force('x', forceX(0).strength(0.05))
    .force('y', forceY(0).strength(0.05))
    .force('z', forceZ(0).strength(0.05))
    .stop()

  for (let i = 0; i < SETTLE_TICKS; i++) sim.tick()

  const out = new Map<string, LaidOutNode>()
  for (const n of simNodes as (Node & { x: number; y: number; z: number })[]) {
    out.set(n.id, { ...n, x: n.x, y: n.y, z: n.z, status: statuses[n.id] ?? 'unverified' })
  }
  return out
}
```

- [ ] **Step 6: Write `frontend/src/scene/Node.tsx`**

```tsx
import { useState } from 'react'
import { nodeColor } from '../lib/severity'
import type { LaidOutNode } from './layout'

export function Node({ node, onSelect }: { node: LaidOutNode; onSelect: (id: string) => void }) {
  const [hovered, setHovered] = useState(false)
  const { color, emissiveIntensity } = nodeColor(node.status)

  return (
    <mesh
      position={[node.x, node.y, node.z]}
      onClick={(e) => { e.stopPropagation(); onSelect(node.id) }}
      onPointerOver={(e) => { e.stopPropagation(); setHovered(true); document.body.style.cursor = 'pointer' }}
      onPointerOut={() => { setHovered(false); document.body.style.cursor = 'auto' }}
    >
      <sphereGeometry args={[0.55, 24, 24]} />
      <meshStandardMaterial
        color={color}
        emissive={color}
        emissiveIntensity={hovered ? emissiveIntensity + 0.4 : emissiveIntensity}
        roughness={0.35}
        metalness={0.2}
      />
    </mesh>
  )
}
```

- [ ] **Step 7: Write `frontend/src/scene/Edge.tsx`**

```tsx
import { useMemo } from 'react'
import * as THREE from 'three'

const UP = new THREE.Vector3(0, 1, 0)

export function Edge({ from, to }: { from: [number, number, number]; to: [number, number, number] }) {
  const { position, quaternion, length } = useMemo(() => {
    const a = new THREE.Vector3(...from)
    const b = new THREE.Vector3(...to)
    const dir = new THREE.Vector3().subVectors(b, a)
    const len = dir.length()
    const mid = a.clone().add(b).multiplyScalar(0.5)
    const quat = new THREE.Quaternion().setFromUnitVectors(UP, dir.normalize())
    return { position: mid, quaternion: quat, length: len }
  }, [from, to])

  return (
    <mesh position={position} quaternion={quaternion}>
      <cylinderGeometry args={[0.02, 0.02, length, 6]} />
      <meshStandardMaterial color="#2A3040" roughness={0.6} metalness={0.1} />
    </mesh>
  )
}
```

- [ ] **Step 8: Write `frontend/src/scene/Graph.tsx`**

```tsx
import { Bounds, OrbitControls } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { Bloom, EffectComposer } from '@react-three/postprocessing'
import { useMemo } from 'react'
import type { Edge as EdgeT, Node as NodeT } from '../api'
import type { DriftStatus } from '../lib/severity'
import { computeLayout } from './layout'
import { Edge } from './Edge'
import { Node } from './Node'

export function Graph({ nodes, edges, statuses, onSelect }: {
  nodes: NodeT[]
  edges: EdgeT[]
  statuses: Record<string, DriftStatus>
  onSelect: (id: string) => void
}) {
  const laidOut = useMemo(() => computeLayout(nodes, edges, statuses), [nodes, edges, statuses])

  return (
    <Canvas camera={{ position: [0, 0, 12], fov: 50 }} dpr={[1, 2]}>
      <color attach="background" args={['#05060B']} />
      <ambientLight intensity={0.5} />
      <directionalLight position={[6, 8, 6]} intensity={1.1} />

      <Bounds key={`${nodes.length}-${edges.length}`} fit clip margin={1.5}>
        {edges.map((e) => {
          const a = laidOut.get(e.from_node)
          const b = laidOut.get(e.to_node)
          if (!a || !b) return null
          return <Edge key={`${e.from_node}-${e.to_node}`} from={[a.x, a.y, a.z]} to={[b.x, b.y, b.z]} />
        })}
        {[...laidOut.values()].map((n) => (
          <Node key={n.id} node={n} onSelect={onSelect} />
        ))}
      </Bounds>

      <OrbitControls enableDamping autoRotate={false} makeDefault />

      <EffectComposer>
        <Bloom luminanceThreshold={0.6} luminanceSmoothing={0.3} intensity={0.8} mipmapBlur />
      </EffectComposer>
    </Canvas>
  )
}
```

- [ ] **Step 9: Wire `Graph` into `frontend/src/App.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { getWorkspace, type Workspace } from './api'
import type { DriftStatus } from './lib/severity'
import { Graph } from './scene/Graph'

const FIXTURE_ID = 'phase0-fixture-workspace'

export function App() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [statuses] = useState<Record<string, DriftStatus>>({})

  useEffect(() => {
    getWorkspace(FIXTURE_ID).then(setWorkspace)
  }, [])

  return (
    <div className="app">
      <div className="hud-top">
        <div className="brand">parity<span>.</span></div>
      </div>
      {workspace && (
        <Graph nodes={workspace.nodes} edges={workspace.edges} statuses={statuses} onSelect={() => {}} />
      )}
    </div>
  )
}
```

- [ ] **Step 10: Typecheck and build**

Run: `npx tsc -b && npx vite build`
Expected: clean.

- [ ] **Step 11: Live-verify in a real browser**

Start the backend (`cd backend && .venv/bin/uvicorn app.main:app --port 8123 &`)
and the frontend (`cd frontend && npm run dev`). Open the dev URL. Expected:
5 spheres render, connected by 3 edges, all neutral-gray (every status is
`unverified` — Task 7 wires up Send). Orbit controls work (drag rotates).

- [ ] **Step 12: Commit**

```bash
git add src/scene/ src/lib/severity.ts src/lib/severity.test.ts src/App.tsx
git commit -m "frontend: real 3D graph render from the fixture workspace"
```

---

### Task 6: Click-to-detail panel

**Files:**
- Create: `frontend/src/lib/useModalPanel.ts`
- Create: `frontend/src/components/DetailPanel.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Produces (`useModalPanel.ts`): `export function useModalPanel(active:
  boolean, onClose: () => void): RefObject<HTMLButtonElement>` — focus/
  inert/Escape handling, reusable by any future panel.
- Produces (`DetailPanel.tsx`): `<DetailPanel node={Node | null} status
  onClose />`.

- [ ] **Step 1: Write `frontend/src/lib/useModalPanel.ts`**

```ts
import { useEffect, useRef } from 'react'

/** Focus/inert/Escape handling for a slide-in panel — native `inert`
 * instead of a hand-rolled focus trap, focus returned on close. */
export function useModalPanel(active: boolean, onClose: () => void) {
  const closeRef = useRef<HTMLButtonElement>(null)
  const returnFocusTo = useRef<Element | null>(null)

  useEffect(() => {
    if (!active) return
    returnFocusTo.current = document.activeElement
    closeRef.current?.focus()

    const root = document.querySelector('.scene-root')
    root?.setAttribute('inert', '')

    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      root?.removeAttribute('inert')
      ;(returnFocusTo.current as HTMLElement | null)?.focus?.()
    }
  }, [active, onClose])

  return closeRef
}
```

- [ ] **Step 2: Write `frontend/src/components/DetailPanel.tsx`**

```tsx
import type { Node } from '../api'
import type { DriftStatus } from '../lib/severity'
import { useModalPanel } from '../lib/useModalPanel'

export function DetailPanel({ node, status, onClose }: {
  node: Node | null
  status: DriftStatus
  onClose: () => void
}) {
  const closeRef = useModalPanel(node !== null, onClose)
  if (!node) return null

  return (
    <div className="dive-backdrop" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="dive" role="dialog" aria-modal="true" aria-labelledby="detail-title">
        <button type="button" className="dive__close" onClick={onClose} ref={closeRef} aria-label="Close detail panel">
          Close ✕
        </button>
        <p className="eyebrow">{node.method} · {node.path_template}</p>
        <h3 id="detail-title" className="dive__title">{node.operation_id}</h3>
        <p className={`dive__status dive__status--${status}`}>{status}</p>
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
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Append detail-panel styles to `frontend/src/styles.css`**

```css
.scene-root{position:relative;width:100%;height:100%}

.dive-backdrop{position:fixed;inset:0;z-index:20;
  background:rgba(5,6,11,.6);backdrop-filter:blur(3px);
  display:flex;justify-content:flex-end}
.dive{width:min(420px,92vw);height:100%;background:#0A0C14;
  border-left:1px solid var(--hair);padding:32px 30px;overflow-y:auto;position:relative}
.dive__close{position:absolute;top:24px;right:24px;background:transparent;
  border:1px solid var(--hair);color:var(--paper);font-family:var(--mono);
  font-size:10px;padding:6px 12px;border-radius:2px;cursor:pointer}
.dive__close:hover{border-color:var(--match);color:var(--match)}
.eyebrow{font-family:var(--mono);font-size:11px;color:var(--mute);margin-bottom:6px}
.dive__title{font-family:var(--disp);font-size:20px;font-weight:700;margin-bottom:10px}
.dive__status{display:inline-block;font-family:var(--mono);font-size:11px;
  text-transform:uppercase;padding:4px 10px;border-radius:2px;margin-bottom:20px}
.dive__status--matched{color:var(--match);border:1px solid var(--match)}
.dive__status--violated{color:var(--violate);border:1px solid var(--violate)}
.dive__status--unverified{color:var(--mute);border:1px solid var(--hair)}
.dive__label{font-family:var(--mono);font-size:10px;color:var(--mute);
  text-transform:uppercase;margin:16px 0 6px}
.dive__schema{background:rgba(255,255,255,.03);border-radius:2px;padding:12px;
  font-family:var(--mono);font-size:11px;color:var(--paper);overflow-x:auto}
```

- [ ] **Step 4: Wire the panel into `frontend/src/App.tsx`**, wrap the
  graph in `.scene-root`, and add `selectedId` state:

```tsx
import { useEffect, useState } from 'react'
import { getWorkspace, type Workspace } from './api'
import { DetailPanel } from './components/DetailPanel'
import type { DriftStatus } from './lib/severity'
import { Graph } from './scene/Graph'

const FIXTURE_ID = 'phase0-fixture-workspace'

export function App() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [statuses] = useState<Record<string, DriftStatus>>({})
  const [selectedId, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    getWorkspace(FIXTURE_ID).then(setWorkspace)
  }, [])

  const selected = workspace?.nodes.find((n) => n.id === selectedId) ?? null

  return (
    <div className="app">
      <div className="scene-root">
        <div className="hud-top">
          <div className="brand">parity<span>.</span></div>
        </div>
        {workspace && (
          <Graph nodes={workspace.nodes} edges={workspace.edges} statuses={statuses} onSelect={setSelectedId} />
        )}
      </div>
      <DetailPanel node={selected} status={selectedId ? (statuses[selectedId] ?? 'unverified') : 'unverified'} onClose={() => setSelectedId(null)} />
    </div>
  )
}
```

- [ ] **Step 5: Typecheck and live-verify**

Run: `npx tsc -b`. Then in the running dev server, click a node — the
panel should slide in from the right showing its method/path/schema,
Escape or the backdrop should close it, and focus should return to the
graph (tab order not trapped inside the closed panel).

- [ ] **Step 6: Commit**

```bash
git add src/lib/useModalPanel.ts src/components/DetailPanel.tsx src/App.tsx src/styles.css
git commit -m "frontend: click-to-detail panel with focus/inert/Escape handling"
```

---

### Task 7: The (fake) Send interaction

**Files:**
- Modify: `frontend/src/components/DetailPanel.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: `sendRequest` from `api.ts` (Task 4).
- `DetailPanel` gains a required `onSend: (nodeId: string) => void` prop
  and renders a "Send" button; `App.tsx` owns the `statuses` state as
  real `useState` (replacing Task 5/6's placeholder empty object) and the
  latest `SendResult` for display.

- [ ] **Step 1: Add the Send button and result display to `DetailPanel.tsx`**

Modify the component signature and add a button plus a real-result block:

```tsx
import { useState } from 'react'
import type { Node, SendResult } from '../api'
import type { DriftStatus } from '../lib/severity'
import { useModalPanel } from '../lib/useModalPanel'

export function DetailPanel({ node, status, onClose, onSend }: {
  node: Node | null
  status: DriftStatus
  onClose: () => void
  onSend: (nodeId: string) => Promise<SendResult>
}) {
  const closeRef = useModalPanel(node !== null, onClose)
  const [result, setResult] = useState<SendResult | null>(null)
  const [sending, setSending] = useState(false)

  if (!node) return null

  async function handleSend() {
    setSending(true)
    try {
      const r = await onSend(node!.id)
      setResult(r)
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="dive-backdrop" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="dive" role="dialog" aria-modal="true" aria-labelledby="detail-title">
        <button type="button" className="dive__close" onClick={onClose} ref={closeRef} aria-label="Close detail panel">
          Close ✕
        </button>
        <p className="eyebrow">{node.method} · {node.path_template}</p>
        <h3 id="detail-title" className="dive__title">{node.operation_id}</h3>
        <p className={`dive__status dive__status--${status}`}>{status}</p>

        <button type="button" className="dive__send" onClick={handleSend} disabled={sending}>
          {sending ? 'Sending…' : 'Send'}
        </button>

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
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Append Send-button/result styles to `styles.css`**

```css
.dive__send{display:block;background:transparent;border:1px solid var(--match);
  color:var(--match);font-family:var(--mono);font-size:11px;padding:8px 16px;
  border-radius:2px;cursor:pointer;margin-bottom:20px}
.dive__send:hover:not(:disabled){background:var(--match);color:var(--ink)}
.dive__send:disabled{opacity:.5;cursor:not-allowed}
.dive__result{background:rgba(255,255,255,.02);border:1px solid var(--hair);
  border-radius:3px;padding:14px;margin-bottom:20px}
.dive__detail{font-size:12px;line-height:1.6;color:var(--mute);margin-top:8px}
```

- [ ] **Step 3: Wire real status state and the send handler into `App.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { getWorkspace, sendRequest, type Workspace } from './api'
import { DetailPanel } from './components/DetailPanel'
import type { DriftStatus } from './lib/severity'
import { Graph } from './scene/Graph'

const FIXTURE_ID = 'phase0-fixture-workspace'

export function App() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [statuses, setStatuses] = useState<Record<string, DriftStatus>>({})
  const [selectedId, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    getWorkspace(FIXTURE_ID).then(setWorkspace)
  }, [])

  const selected = workspace?.nodes.find((n) => n.id === selectedId) ?? null

  async function handleSend(nodeId: string) {
    const result = await sendRequest(FIXTURE_ID, nodeId)
    setStatuses((prev) => ({ ...prev, [nodeId]: result.drift_finding.status }))
    return result
  }

  return (
    <div className="app">
      <div className="scene-root">
        <div className="hud-top">
          <div className="brand">parity<span>.</span></div>
        </div>
        {workspace && (
          <Graph nodes={workspace.nodes} edges={workspace.edges} statuses={statuses} onSelect={setSelectedId} />
        )}
      </div>
      <DetailPanel
        node={selected}
        status={selectedId ? (statuses[selectedId] ?? 'unverified') : 'unverified'}
        onClose={() => setSelectedId(null)}
        onSend={handleSend}
      />
    </div>
  )
}
```

- [ ] **Step 4: Typecheck**

Run: `npx tsc -b`
Expected: clean.

- [ ] **Step 5: Live-verify the full loop in a real browser**

With backend + frontend both running: click the `create_task` node (POST
`/tasks`), click Send, confirm the panel shows a 201 response body missing
`done` and a `violated` status with the real detail text, **and** confirm
the node itself turns red/violate-colored in the 3D graph after closing
the panel. Click `get_task`, Send, confirm it turns green/matched.

- [ ] **Step 6: Commit**

```bash
git add src/components/DetailPanel.tsx src/App.tsx src/styles.css
git commit -m "frontend: wire the (fake) Send interaction, nodes update live"
```

---

### Task 8: CI, HANDOFF.md, final live-verification

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `HANDOFF.md`

**Interfaces:** None — this task wires up automation and documentation
around the already-complete Phase 0 slice; no new application code.

- [ ] **Step 1: Write `.github/workflows/ci.yml`**

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97  # v7.0.0
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: pytest -q

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
      - uses: actions/setup-node@v5
        with:
          node-version: "22"
      - run: npm install
      - run: npm test
      - run: npm run build
```

- [ ] **Step 2: Run the full local test suite one more time**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: 9 passed.
Run: `cd frontend && npx vitest run && npx tsc -b && npx vite build`
Expected: 3 passed, clean typecheck, clean build.

- [ ] **Step 3: Write `HANDOFF.md`**

```markdown
# parity — HANDOFF

**Read this first if picking this up in a new session.** Same role as
`loom`'s own `HANDOFF.md`: what's done, what's next, decisions made along
the way. Read `SPEC.md` first regardless — it's the real architecture doc.

## <TODAY'S DATE>: Phase 0 walking skeleton — done, live-verified

**What's running**: a FastAPI backend serving one hand-written fixture
workspace (5 REST-operation nodes, a small task-manager API) over the real
Phase-1 route shapes (`SPEC.md` §7.6), with a fake `POST
/api/workspaces/{id}/requests` returning a canned, deterministic result
per node — no real OpenAPI/GraphQL parsing, no real request proxying yet.
A Vite + React + R3F frontend renders that workspace as a real 3D graph
(nodes grouped by shared path via `d3-force-3d`, camera auto-fit via
`Bounds`), with a working click → detail panel → Send → node-color-updates
loop, on a new standalone visual identity (not the portfolio's or `loom`'s
tokens — see `docs/superpowers/plans/2026-09-10-phase0-walking-skeleton.md`'s
Global Constraints for the exact values).

### Verified

- Backend: `cd backend && .venv/bin/python -m pytest -q` — 9 passed.
- Frontend: `cd frontend && npx vitest run` — 3 passed. `npx tsc -b` and
  `npx vite build` both clean.
- **Live-verified in a real browser**: 5 nodes render correctly clustered
  by shared path, orbit controls work, clicking a node opens the detail
  panel with its real declared schema, Send against `create_task` shows a
  real (fake) `violated` result with the real missing-field detail text
  and the node turns red in the graph; Send against `get_task` shows
  `matched` and the node turns green. Escape and backdrop-click both close
  the panel; focus returns to the graph afterward.

### Run it locally

\`\`\`
cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --port 8123

cd frontend && npm install && npm run dev
\`\`\`

### Next (Phase 1, SPEC.md §10)

Real OpenAPI parsing (URL + file upload) and real GraphQL introspection +
SDL parsing, real Postgres persistence of workspaces/nodes (with the
Phase-1 default-system-user approach SPEC.md's Phase 1 section describes
for `workspace.user_id` before real accounts exist). No request-firing
yet — every node stays honestly `unverified` until Phase 2.
```

Replace `<TODAY'S DATE>` with the actual date this task is executed.

- [ ] **Step 4: Commit and push**

```bash
git add .github/workflows/ci.yml HANDOFF.md
git commit -m "chore: CI workflow + HANDOFF.md for Phase 0"
git fetch origin
git log HEAD..origin/main --oneline   # confirm empty before pushing
git push origin main
```

- [ ] **Step 5: Confirm CI is green**

Run: `gh run list --repo MaXiMo000/parity --limit 1` then
`gh run watch <run-id> --repo MaXiMo000/parity --exit-status`
Expected: both `backend` and `frontend` jobs pass.
