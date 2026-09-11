# parity — HANDOFF

**Read this first if picking this up in a new session.** Same role as
`loom`'s own `HANDOFF.md`: what's done, what's next, decisions made along
the way. Read `SPEC.md` first regardless — it's the real architecture doc.

## 2026-09-11: Phase 0 walking skeleton — done, live-verified

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
  the panel; focus returns to whatever was focused before the panel opened
  (often `<body>`, since `<Canvas>` isn't keyboard-focusable — there's no
  keyboard path to select a node yet, pointer-only).

### Run it locally

```
cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --port 8123

cd frontend && npm install && npm run dev
```

### Next (Phase 1, SPEC.md §10)

Real OpenAPI parsing (URL + file upload) and real GraphQL introspection +
SDL parsing, real Postgres persistence of workspaces/nodes (with the
Phase-1 default-system-user approach SPEC.md's Phase 1 section describes
for `workspace.user_id` before real accounts exist). No request-firing
yet — every node stays honestly `unverified` until Phase 2.

## 2026-09-11: Phase 1a OpenAPI + Postgres persistence — done, live-verified

**What's running**: real Postgres persistence of workspaces and API nodes via
SQLAlchemy ORM and Alembic migrations, with a Phase-1-spec default system
user (no user accounts yet — every request uses the single system user until
OAuth/SSO exists in Phase 3+). Real OpenAPI ingestion: paste a spec URL or raw
JSON/YAML, the backend fetches and validates with `openapi-spec-validator`,
resolves every `$ref` inline to flatten the schema graph, extracts operation
nodes (filtered to first-2xx-only response schemas for simplicity), and stores
in the database. The `POST /api/workspaces/{id}/requests` route now honestly
returns 501 (Not Implemented) instead of Phase 0's fake `violated`/`matched`
result. Live-verified against `https://petstore3.swagger.io/api/v3/openapi.json`:
real 19 operation nodes + 16 inter-operation reference edges render in 3D,
schemas in the detail panel are the real resolved `$ref`-flattened inline
schemas, Send button shows the honest 501. (GraphQL parsing — Phase 1b — is
**not** in this release; SPEC.md Phase 1 covers both OpenAPI and GraphQL, but
this task plan intentionally split them; Phase 1b is a separate upcoming task.)

### Decisions

- **Postgres for persistence**: replaced Phase 0's in-memory fixture with
  durable state. Alembic for migrations. `user_id` is hardcoded to the system
  user (id=1) until Phase 3.
- **OpenAPI validation exception handling**: `openapi-spec-validator` has
  multiple exception types (e.g. `ValidatorError`, `SpecificationError`,
  spec format errors) that don't share a common base. The catch is deliberately
  broad (`except Exception`) — catching specific types would miss real validation
  failures and misdiagnose them as 500s. This is a known simplification; if
  we later need finer error classification, the spec-validator library itself
  would need to be patched upstream or wrapped with a shim.
- **First-2xx-only schemas**: OpenAPI specs often declare many response codes
  (4xx, 5xx, default). For MVP clarity, we extract only 2xx responses and take
  the first one. Revisit this in Phase 2 if request scenarios need 400/404
  simulation.
- **No request-sending yet**: the 501 is honest. Firing real requests against
  the remote API is Phase 2 (Spec §11). Every node remains `unverified` state.

### Verified

- Backend: `cd backend && .venv/bin/python -m pytest -q` — 19 passed (up from
  Phase 0's 9; new tests cover Postgres persistence, OpenAPI parsing, node
  extraction, default-user mechanism).
- Frontend: `cd frontend && npx vitest run` — 5 passed (no new tests; existing
  render/interaction tests still passing). `npx tsc -b` clean. `npx vite build`
  successful (expected chunk-size warning for a 3D graph library is not a blocker).
- **Live-verified in a real browser**: opened the app, created a workspace
  via the form with `https://petstore3.swagger.io/api/v3/openapi.json`,
  backend fetched, validated, parsed, and stored 19 nodes in the database;
  frontend fetched and rendered the graph in 3D with correct resolved
  schemas in each node's detail panel; clicked Send on any node, saw the
  honest 501 response with correct message and formatting. (There is no
  workspace-list/picker UI yet — see the gap noted below.)

### Run it locally

```
cd backend
docker compose up -d
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/alembic upgrade head
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/uvicorn app.main:app --port 8123

cd frontend && npm install && npm run dev
# browse to localhost:5173, create a workspace via the form (name + OpenAPI URL)
```

`app/main.py`'s startup hook only calls `ensure_default_user` — it does
**not** create tables. `docker compose up` and a real `alembic upgrade
head` against the running Postgres are both required before `uvicorn` will
serve real requests.

### Known gap for Phase 1b

No workspace-list/picker UI yet — every persisted workspace is currently
only reachable by re-creating it (re-parsing its URL again). `listWorkspaces`
and `WorkspaceSummary` in `frontend/src/api.ts` are exported and the backend
route works, but nothing in the UI calls them. Phase 1b or a small follow-up
should add a real list view.

### Next (Phase 1b and beyond, SPEC.md §11–13)

Phase 1b will add GraphQL SDL + introspection parsing (same shape: fetch URL,
validate, extract operation nodes, store). Phase 2 will implement honest
request-sending against real remote APIs and state tracking (node → verified
or error). Phase 3+ will add user accounts, OAuth, and per-user workspaces.
