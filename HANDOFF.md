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
real 19 operation nodes + 16 inter-operation path-template-derived edges render in 3D,
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

## 2026-09-11: Phase 1b: GraphQL Schema Parsing — done, live-verified

**What/Why**: Phase 1a covered OpenAPI only; SPEC.md's Phase 1 scope also
requires GraphQL. This phase adds the second schema kind end-to-end — real
introspection/SDL parsing, a `schema_kind` selector on workspace creation,
and a frontend detail panel that renders GraphQL fields correctly instead
of the OpenAPI-shaped `null · null` placeholder.

**What was built**: `fetch_introspection` (live GraphQL endpoints, via the
standard introspection query) and `parse_graphql` (raw SDL text), both built
on `graphql-core`, extract one `Node` per field on the schema's `Query` and
`Mutation` root types — `Subscription` fields are explicitly out of scope
for v1. `POST /api/workspaces` accepts `schema_kind: "graphql"` alongside
the existing `"openapi"` and routes to the GraphQL parser. The frontend
gained a kind selector (OpenAPI / GraphQL) on the create-workspace form,
and the node detail panel now derives its eyebrow/title from the node's
real `kind`/`name` (e.g. `Query field` / `country`) instead of assuming
OpenAPI's `method`/`path` shape, with the field's declared argument and
response type descriptors shown as JSON.

### Known simplifications

- **No GraphQL edges yet**: nodes are extracted per root-type field with no
  inter-node relationship graph — the 3D view renders them as an
  unconnected cluster (no visible edges), unlike OpenAPI's
  path-template-derived edges (see `app/edges.py`'s docstring: edges are
  computed purely from `path_template` — grouped by first path segment,
  sorted by path length, chained consecutively — never from `$ref`
  resolution, which only ever affects a node's declared schemas, not
  edges). A real type-relationship layout for GraphQL mode is SPEC.md §8.3
  frontend work, not attempted in this phase.
- **`Subscription` out of scope**: only `Query` and `Mutation` root-type
  fields become nodes; real-time subscription operations are not
  represented at all in v1.
- **No request-sending yet**: same honest 501 from Phase 1a — GraphQL nodes
  are just as `unverified` as OpenAPI ones until Phase 2 fires real
  requests.
- **`declared_request_schema`/`declared_response_schema` hold different
  shapes depending on `node.kind`**: for REST nodes (`kind:
  "rest_operation"`) these are real JSON Schema, with every `$ref` resolved
  inline. For GraphQL nodes (`kind: "graphql_field"`) they are not JSON
  Schema at all — `declared_request_schema` is `{argName: typeDescriptor}`
  (a map of the field's arguments, not a schema object), and
  `declared_response_schema` is a single type descriptor:
  `{"kind": "NAMED", "name": str, "nullable": bool}` or `{"kind": "LIST",
  "of": <descriptor>, "nullable": bool}`. This is deliberate, not a bug —
  GraphQL types aren't JSON Schema, and forcing a translation would lose
  nullability precision — but it means any caller reading these two
  columns must branch on `node.kind` before interpreting them. Phase 2's
  drift-checker (the direct consumer, per SPEC.md §7.2/§10) needs to know
  this going in.

### Verified

- Backend: `cd backend && .venv/bin/python -m pytest -q` — **32 passed**
  (up from Phase 1a's 21: Task 1's 7 new GraphQL-parsing tests + Task 2's 4
  new route/integration tests).
- Frontend: `cd frontend && npx vitest run` — **7 passed** across 3 test
  files (up from Phase 1a's 5: Task 3's 2 new `nodeLabel` tests covering
  the GraphQL-shaped detail-panel title/eyebrow derivation).
- **Live-verified in a real browser** (backend on `:8123` against real
  Postgres via `docker compose` + `alembic upgrade head`, frontend
  `npm run dev` on `:5173`, driven with an actual browser, not simulated):
  - Created a workspace named "Countries GraphQL", kind `GraphQL`, URL
    `https://countries.trevorblades.com/graphql` (a real public GraphQL
    API). Backend fetched, introspected, and persisted **6 real nodes**
    with no errors (`POST /api/workspaces` → 201, `GET
    /api/workspaces/{id}` → 200, confirmed 6 nodes via the API response).
  - The 3D graph rendered exactly 6 nodes, clustered with no visible edges
    — the stated, known v1 limitation above, not a bug.
  - Clicked a node (`country`, one of the schema's `Query` fields) and the
    detail panel opened showing `Query field` as the eyebrow and `country`
    as the title (not `null · null`), with its real declared argument
    (`code: ID!`) and response type (`Country`, nullable) descriptors
    rendered as JSON.
  - Clicked Send on that node and got the honest, unchanged `501`:
    `{"detail":"real request execution arrives in Phase 2 (SPEC.md
    §7.3/§10)"}`.
  - **Regression-checked the OpenAPI path**: created a second workspace,
    kind `OpenAPI`, URL `https://petstore3.swagger.io/api/v3/openapi.json`.
    Backend responded 201/200 with no errors and persisted 19 nodes + 16
    edges — matching Phase 1a's known result exactly, confirming the
    GraphQL work didn't regress OpenAPI parsing.

### Known gap for Phase 2 (carried over / still open)

- No workspace-list/picker UI yet — unchanged from Phase 1a. Every
  persisted workspace (OpenAPI or GraphQL) is still only reachable by
  re-creating it.
- GraphQL nodes render with no edges — a real type-relationship graph
  layout for GraphQL mode (SPEC.md §8.3) is frontend work not attempted in
  this phase.

### Next (Phase 2, SPEC.md §10–11)

Real request execution against both REST and GraphQL targets, through a
full SSRF-hardened proxy, and real drift-checking (comparing live response
shapes against each node's declared schema) — replacing the honest 501
with actual verified/violated states.
