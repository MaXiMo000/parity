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

## 2026-09-11: Phase 1c: SSRF Hardening + Workspace List — done, live-verified

**What/Why**: Phase 1b's final review parked two Minor findings in the
SSRF guard used by `fetch_spec`/`fetch_introspection`, and Phase 1a/1b both
carried forward the same named UI gap (no way to reopen a persisted
workspace). This phase closes all three.

**What was built**:

- **DNS-pinning fix**: `_resolve_safe_ip`/`_build_pinned_request` (`app/schema/openapi.py`)
  now resolve a spec URL's hostname, validate every resolved address is
  globally routable, and then build the real `httpx.Request` to connect
  **directly to that validated IP** — with the original hostname preserved
  as the `Host` header and TLS SNI (`extensions={"sni_hostname": ...}`) so
  the request is indistinguishable from an ordinary one to the target
  server. This closes the specific DNS-rebinding TOCTOU window Phase 1b's
  final review flagged as a parked Minor: previously the guard validated
  a hostname's resolved address, then let `httpx` re-resolve independently
  at connect time — a hostname that resolves safely on the validation
  lookup and unsafely on httpx's own lookup a moment later would have
  slipped through.
- **CGNAT fix**: the same guard now rejects `100.64.0.0/10` (RFC 6598),
  real internal address space at several cloud providers, which the old
  `is_private`/`is_loopback`/`is_link_local`/`is_reserved` checks missed
  entirely. The fix replaces that check list with Python's stdlib
  `ipaddress.ip_address(ip).is_global`, which correctly subsumes all four
  old checks and additionally covers CGNAT.
- **Workspace-list/picker UI**: a `WorkspaceList` component
  (`frontend/src/components/WorkspaceList.tsx`) adds a "Load existing…"
  `<select>` populated from `listWorkspaces`, wired to an `onLoad` handler
  in `App.tsx` that calls `getWorkspace(id)` and re-renders the graph —
  closing the gap named in Phase 1a's HANDOFF ("No workspace-list/picker
  UI yet... every persisted workspace is currently only reachable by
  re-creating it") and carried through Phase 1b's.

**What this is *not***: this still isn't SPEC.md §7.3's fuller Phase-2
sandboxed-proxy mitigation. That mitigation covers real request
*execution* against arbitrary user-supplied target APIs (Phase 2's
Send-button work) — a different, larger surface than schema *fetching*,
which is all this phase touches. Nobody should read this phase as having
finished §7.3.

### Verified

- Backend: `cd backend && .venv/bin/python -m pytest -q` — **38 passed**
  (real output, confirmed 2026-09-11; up from Phase 1b's 32).
- Frontend: `cd frontend && npx vitest run` — **7 passed** across 3 test
  files (real output, confirmed 2026-09-11; unchanged from Phase 1b's
  count — the picker is covered by live verification below rather than
  new unit tests).
- **Live-verified in a real browser** (backend on `:8123` against real
  Postgres via `docker compose` + `alembic upgrade head`, frontend
  `npm run dev` on `:5173`, driven with an actual browser, not simulated):
  - Created a workspace named "Petstore OpenAPI", kind OpenAPI, URL
    `https://petstore3.swagger.io/api/v3/openapi.json`. `POST
    /api/workspaces` → 201, `GET /api/workspaces/{id}` → 200 with the real
    19 nodes (matching Phase 1a's known result), and the 3D graph rendered
    the same ring-shaped, edge-connected layout as before — confirming the
    DNS-pinning rewrite didn't break real external fetches, only tightened
    what it accepts.
  - Created a second workspace named "Countries GraphQL", kind GraphQL,
    URL `https://countries.trevorblades.com/graphql`. `POST
    /api/workspaces` → 201, `GET /api/workspaces/{id}` → 200 with the real
    6 nodes (matching Phase 1b's known result) — same confirmation for the
    GraphQL path.
  - Confirmed the "Load existing…" picker listed both workspaces by name
    and kind: "Petstore OpenAPI (openapi)" and "Countries GraphQL
    (graphql)". Selected the first one; a fresh `GET
    /api/workspaces/{petstore-id}` fired and the graph reloaded to show
    the Petstore ring layout — confirming the picker's `onLoad` →
    `getWorkspace` round-trip works for real, not just against mocked
    tests.
  - Did a full browser refresh (`navigate` to `http://localhost:5173`,
    not a client-side route change). The app reset to its empty state (no
    workspace auto-selected) but the "Load existing…" picker still listed
    both "Petstore OpenAPI (openapi)" and "Countries GraphQL (graphql)" —
    confirming they're really in Postgres, not component state.

### Known gaps (carried over / still open)

- Carried from Phase 1b: GraphQL nodes still render with no edges in the
  3D graph (a real type-relationship graph layout for GraphQL mode is
  SPEC.md §8.3 frontend work, not yet attempted).
- New from this phase's own final review (documented, not fixed — each
  with why):
  - `send_pinned` forwards headers/body unchanged across a redirect hop;
    safe today since neither caller passes credentials, but Phase 2's
    request-execution proxy must not reuse it unmodified for
    authenticated requests without addressing this first (see the
    docstring note added by this phase's final-review fix).
  - SPEC.md §9 names a dedicated `app/proxy/ssrf_guard.py` module for the
    SSRF guard; it currently lives in `app/schema/openapi.py` for
    schema-parsing convenience. Phase 2 should extract it when building
    the real request-execution proxy.
  - The current per-operation `httpx.Client(timeout=15.0)` isn't a true
    hard wall-clock cap (a slow-drip response can hold a connection close
    to 15s per hop) and there's no response-size cap — both named
    explicitly in SPEC.md §7.3 as needed for Phase 2's fuller mitigation.
  - Pinning to the first resolved address (rather than trying every
    address `getaddrinfo` returns) means a dual-stack host whose
    first-returned address happens to be unreachable now fails the fetch
    outright, where it previously might have succeeded via a later
    address — an availability tradeoff, not a security one.
  - The workspace picker degrades silently (renders nothing) if
    `listWorkspaces()` fails, rather than surfacing an error — acceptable
    since it degrades to the pre-Phase-1c UI state and the picker is a
    convenience affordance with a working alternative (re-creating the
    workspace).

### Next (Phase 2, SPEC.md §10–11)

Real request execution against both REST and GraphQL targets, through the
full SSRF-hardened proxy (SPEC.md §7.3's sandboxed-proxy mitigation, not
yet built), and real drift-checking (comparing live response shapes
against each node's declared schema) — replacing the honest 501 with
actual verified/violated states.

## 2026-09-11: Phase 2a: Real Request Execution + REST Drift-Checking — done, live-verified

**What/Why**: Phase 1c closed out schema-fetching SSRF hardening and the
workspace picker; the honest 501 from every prior phase was still the only
thing the Send button could produce. This phase replaces it with real
request execution end to end: a hardened outbound proxy, a real curl
parser, REST request-to-node matching, and real `jsonschema`-based drift
validation — wired into the real routes.

**What was built**:

- **SSRF-guarded outbound proxy** (`app/proxy/ssrf_guard.py`,
  `app/proxy/client.py`): extracted from Phase 1c's schema-fetch guard
  into its own module (closing the gap that phase's HANDOFF explicitly
  flagged), reused for real request execution — `fire_request` resolves
  and validates the target host the same DNS-pinned way schema-fetching
  does before connecting, so a request aimed at link-local/private/CGNAT
  address space is rejected before any bytes leave the proxy.
- **Real curl parser** (`app/proxy/curl_parser.py`): a small hand-rolled
  parser over stdlib `shlex.split`, covering exactly the flag set SPEC.md
  §7.1 names (`-X`/`--request`, `-H`/`--header`, `-d`/`--data`/
  `--data-raw`/`--data-binary`, `-u`/`--user`, `-G`, `-b`/`--cookie`).
  `uncurl` (the library SPEC.md §7.1 said to try first) was evaluated
  directly against real devtools-shaped curl commands and rejected for a
  real, verified reason: it conflates `-b` with `--data-binary` (real
  curl's `-b` is `--cookie`; confirmed by reading uncurl's own argparse
  source — `-b` is never mapped to cookies there) and has no `-G` support
  at all, both flags this project explicitly needs. The hand-rolled
  parser is the real decision made against that real finding, not a
  fallback taken on faith.
- **REST request-matching** (`app/matching.py`): matches a fired
  request's method + path back to the Node it corresponds to, scoring a
  literal path segment above a templated one at the same position.
  Verified against a real ambiguity in the Petstore fixture itself:
  `/pet/findByStatus`, `/pet/findByTags`, and `/pet/{petId}` are all real
  2-segment `GET` paths under `/pet` — a naive segment-count-only match
  would let `/pet/{petId}` wrongly claim a request meant for
  `/pet/findByStatus`. Live-verified below: a real request to
  `/pet/findByStatus?status=available` matched the real `findByStatus`
  node, not `/pet/{petId}`.
- **REST drift-checking** (`app/drift/rest.py`): validates the real
  response body against the matched node's declared response schema using
  the real `jsonschema` library (not a hand-rolled shape comparison)
  against the real `$ref`-resolved JSON Schema Phase 1a's OpenAPI parser
  already produces. Returns `matched`, `violated` (with a real
  `json_path`/message detail), or `unverified_no_schema` when the node has
  no declared schema to check against; `unverified_no_match` (a fired
  request that matched no known node) is decided by the route, not this
  function.
- **Real routes** (`app/routes/requests.py`, `app/routes/curl_parse.py`):
  `POST /api/workspaces/{id}/requests` now fires a real proxied request,
  matches it (REST workspaces only — GraphQL matching is Phase 2b), checks
  drift, and persists `Request`/`Response`/`DriftFinding` rows with
  headers redacted before storage, replacing the 501 entirely. `GET
  .../requests` and `GET .../nodes/{node_id}/history` expose that
  persisted history. `POST /api/curl-parse` exposes the curl parser as its
  own endpoint.
- **GraphQL workspaces**: requests fire for real through the same
  SSRF-guarded proxy, but are honestly recorded as `unverified_no_match` —
  no REST-shaped matching or drift-checking is applied to them. Phase 2b
  adds real GraphQL matching + drift validation.

### Verified

- Backend: `cd backend && .venv/bin/python -m pytest -q` — **84 passed**
  (real output, confirmed 2026-09-11 during this phase's own verification
  pass, run a second time independently of Task 6's own count).
- **Live-verified against the backend directly (no frontend/browser
  involved — see the explicit note below)**, with Postgres via `docker
  compose up -d` + `alembic upgrade head`, and `uvicorn app.main:app
  --port 8123` running against it:
  - `POST /api/workspaces` with `schema_source_url:
    https://petstore3.swagger.io/api/v3/openapi.json` → `201`, real 19
    nodes, workspace id `d27a8cbd-6704-468c-b55d-2abcd4427744`.
  - `POST /api/curl-parse` with `curl -X GET
    'https://petstore3.swagger.io/api/v3/pet/findByStatus?status=available'`
    → `{"method":"GET","url":"https://petstore3.swagger.io/api/v3/pet/findByStatus?status=available","headers":{},"body":null}`,
    correctly parsed with no headers/body.
  - `POST /api/workspaces/{id}/requests` with that same GET against the
    **real, live** Petstore API → a real `200` from the live API, the
    request's `node_id` correctly resolved to the real `findByStatus` node
    (`229e0a6a-09d1-4fd2-af69-1f5ea63f1d02`, confirmed via a follow-up
    `GET /api/workspaces/{id}` showing `path_template:
    "/pet/findByStatus"`) — not the ambiguous `/pet/{petId}` node — and a
    real `drift_finding`. **The live Petstore API's actual current
    response did not match its own declared schema**: `drift_finding.status`
    came back `"violated"`, detail `"$[289]: 'name' is a required
    property"` — one entry in the live, shared Petstore demo dataset (a
    publicly-writable sandbox other users' test traffic also mutates) is
    genuinely missing its schema-required `name` field. This is a real,
    unforced result of comparing a real live response to Petstore's own
    real declared schema, not an artifact of this project's code — it is
    reported exactly as it came back.
  - `GET /api/workspaces/{id}/requests` → the one request above, with its
    real `node_id` and timestamp.
  - `GET /api/workspaces/{id}/nodes/{node_id}/history` → the one
    `violated` drift finding above, confirming persisted history.
  - SSRF guard confirmed live (not just in tests): `POST
    /api/workspaces/{id}/requests` targeting `http://169.254.169.254/`
    (the cloud metadata address) returned a real `502`:
    `{"detail":"http://169.254.169.254/ is not a permitted target"}`.
  - `uvicorn` was stopped after this verification pass; Postgres
    (`docker compose`) was left running, as instructed.

**This is backend-level verification only, not browser/frontend
verification.** The frontend still shows the Phase 0/1 UI: a bare "Send"
button with no way to specify method, URL, headers, or body. Clicking it
will currently fail, because it still calls the old
`sendRequest(workspaceId, nodeId)` shape against this phase's new
`{method, url, headers, body}` request body shape. This is a real,
deliberate, temporary state, not an oversight — Phase 2b replaces the
frontend's Send flow with a real request-builder panel that calls this
plan's real endpoint shape (curl-paste UI + history view, SPEC.md §8.4).

### Known gaps (carried over / still open)

- Carried from Phase 1b/1c: GraphQL nodes still render with no edges in
  the 3D graph (SPEC.md §8.3 frontend work, not yet attempted).
- GraphQL workspaces: requests fire for real through the SSRF-guarded
  proxy, but every result is honestly `unverified_no_match` — no
  GraphQL-shaped request matching or drift-checking exists yet.
- The frontend Send button is currently broken against the new endpoint
  shape (see above) — expected and temporary, not a regression to fix in
  this phase.

### Next (Phase 2b, SPEC.md §10)

GraphQL request-matching + drift validation (closing the gap this phase
leaves as honest `unverified_no_match`), and the frontend's real
request-builder panel + curl-paste UI + history view (SPEC.md §8.4),
replacing the currently-broken bare Send button.
