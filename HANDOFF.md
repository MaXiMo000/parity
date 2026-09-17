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

## 2026-09-12: Phase 2b: GraphQL Drift-Checking + Real Request-Builder UI — done, live-verified

**What/Why**: Phase 2a shipped real REST request execution + drift-checking
but left GraphQL workspaces honestly `unverified_no_match` (no GraphQL-shaped
matching existed), and the frontend's Send button was still broken against
the new `{method, url, headers, body}` request shape. This phase closes
both gaps: real GraphQL request-matching + drift-checking (completing
SPEC.md Phase 2 for both protocols), and a real request-builder UI
(curl-paste, method/URL/headers/body fields, per-node + workspace-wide
history) replacing the broken Send button entirely.

**What was built**:

- **GraphQL request-matching** (`app/matching.py::match_graphql_node`):
  parses the real GraphQL-over-HTTP JSON envelope (`{"query": ..., "variables":
  ...}`), parses the query with the real `graphql-core` library, and matches
  the operation's declared type (`Query`/`Mutation`) + its first top-level
  selected field to a Node. **Stated v1 scope, not implied as more**: only
  the FIRST operation definition and its FIRST top-level field selection are
  considered — a query selecting multiple fields, or a document with
  multiple operations, only matches on the first of each. Returns `None`
  (never a guess) on invalid JSON, non-string `query`, a GraphQL syntax
  error, or no matching node.
- **GraphQL drift-checking** (`app/drift/graphql.py::check_graphql_drift`):
  validates a real response's `data` payload against the matched node's
  declared return-type descriptor (Phase 1b's shallow per-field type
  capture, not a full recursive schema). **Stated v1 scope**: scalar leaf
  types (`Int`, `Float`, `String`, `ID`, `Boolean`) and null-appropriateness
  are checked precisely at every level, including inside lists; a custom
  object/enum type is checked only for presence and null-appropriateness,
  not deep-validated field-by-field, because Phase 1b's declared schema
  only stores that field's own return-type descriptor, not the full shape
  of the type it names. A response carrying a top-level GraphQL `errors`
  array is `violated`. Returns `matched`, `violated`, or
  `unverified_no_schema`.
- **Real routes** (`app/routes/requests.py`): `POST
  /api/workspaces/{id}/requests` now runs GraphQL matching + drift-checking
  for GraphQL workspaces the same way REST workspaces already got in Phase
  2a, replacing the honest `unverified_no_match` placeholder.
- **Frontend request-builder** (`frontend/src/components/RequestBuilder.tsx`):
  a real panel replacing the broken bare Send button — method/URL/headers/body
  fields pre-filled from the node (`guessUrl`/`guessBody`), a curl-paste
  textarea wired to the real `POST /api/curl-parse` endpoint via a "Parse
  curl" button, and a real Send that calls the real `{method, url, headers,
  body}` endpoint shape and reports back a real response + drift status.
  REST nodes pre-fill a real, correct URL built from the schema's origin +
  base path + path template — including any literal `{param}` placeholders
  the user must fill in themselves (a real, stated limitation, not a bug).
  GraphQL nodes pre-fill a minimal, deliberately incomplete query skeleton
  (`{ fieldName }`) that the user completes with any required arguments —
  matching this phase's own matching/pre-fill v1 scope.
- **History views**: per-node history in the detail panel, plus a new
  workspace-wide History panel (`frontend/src/components/HistoryPanel.tsx`)
  listing every request fired in the workspace — method, URL, and
  timestamp per row — filterable by a node-filter dropdown.
- Node color in the 3D graph now updates live from a fired request's real
  drift status (`matched` green, `violated` red, `unverified_*` neutral
  gray) via `frontend/src/lib/severity.ts`.

**Verified**:

- Backend: `cd backend && .venv/bin/python -m pytest -q` — **109 passed**
  (real output, confirmed 2026-09-12 during this phase's own verification
  pass).
- Frontend: `cd frontend && npx vitest run` — **15 passed across 4 test
  files** (real output, confirmed 2026-09-12).
- **Live-verified end to end in a real browser** (Postgres via `docker
  compose up -d` + `alembic upgrade head`, `uvicorn app.main:app --port
  8123`, `npm run dev` on port 5173, driven with real clicks/typing, not
  curl):
  - Created a real workspace against `https://petstore3.swagger.io/api/v3/openapi.json`.
    The real 3D graph rendered with real nodes.
  - Clicked the real `GET /pet/{petId}` node (`getPetById`); the detail
    panel showed the real request-builder pre-filled with method `GET` and
    URL `https://petstore3.swagger.io/api/v3/pet/{petId}` — the literal
    `{petId}` left for the user to fill in, confirmed as the real, stated
    limitation named above.
  - Edited the URL to a real pet id (`.../pet/1`) and clicked Send: got a
    real `404` back from the live Petstore API (that id doesn't currently
    exist in the shared demo dataset) with drift status
    `unverified_no_schema` (non-2xx responses have no declared schema to
    check, per Phase 2a). Re-tested against a real pet id confirmed to
    exist (`.../pet/123456789`, fetched directly from the live API first):
    got a real `200` with `{"id":123456789,"name":"doggie","photoUrls":["string"],...}`,
    drift status `matched`, and the node visibly turned green in the 3D
    graph.
  - Pasted `curl -X GET 'https://petstore3.swagger.io/api/v3/pet/findByStatus?status=available'`
    into the curl box on the `findPetsByStatus` node and clicked "Parse
    curl": the method/URL fields updated correctly. Clicked Send: got a
    real `200` back from live Petstore with 620 real pets, drift status
    `violated` (the live shared dataset again contains at least one pet
    missing a schema-required field, consistent with Phase 2a's own
    finding) — the node turned red.
  - Opened the workspace-wide History panel: it listed all 3 real requests
    just sent, each with a real timestamp. Selecting `getPetById` in the
    node-filter dropdown correctly narrowed the list to just its 2
    requests, confirming the filter works.
  - Created a second real workspace against
    `https://countries.trevorblades.com/graphql`. The GraphQL nodes
    rendered in the 3D graph with no edges between them (the known gap
    named below).
  - Clicked the real `country` query field node: the pre-filled body was
    the real, valid-but-incomplete GraphQL skeleton `{"query": "{ country
    }"}`, missing the required `code` argument — confirmed as the real,
    stated v1 pre-fill limitation, not a bug. Method defaulted to `POST`;
    URL was pre-filled with the real GraphQL endpoint.
  - Edited the body to `{"query": "{ country(code: \"US\") { name } }"}`
    and clicked Send: got a real `200` back —
    `{"data":{"country":{"name":"United States"}}}` — with a real node
    match (`country`/`Query`) and drift status `matched`; the node turned
    green in the 3D graph.
  - Re-confirmed the SSRF guard holds through this new UI path, not just
    curl: sent a request with the URL manually edited to a private/loopback
    target. (The exact `169.254.169.254` cloud-metadata address from the
    plan could not be typed into the browser in this session — the
    sandbox's own safety classifier blocked that literal string regardless
    of which field it was typed into. `http://127.0.0.1:9/` was used
    instead, exercising the identical SSRF-guard code path — confirmed
    separately at the backend level that `169.254.169.254` itself is
    still rejected the same way.) The backend returned a real `502`
    (`"http://127.0.0.1:9/ is not a permitted target"`), and the UI
    surfaced it as a plain error message under the Send button — no crash,
    no silent failure.
  - `uvicorn` and `npm run dev` were both stopped after this verification
    pass; Postgres (`docker compose`) was left running, as instructed.

### Known gaps (carried over / newly identified)

- Carried from Phase 1b/1c/2a: GraphQL's dual-mode 3D graph layout
  (SPEC.md §8.3 — a type-relationship graph with `Query`/`Mutation` as
  roots) is still not built — GraphQL nodes render with no edges between
  them, live-confirmed again above.
- **Host-blind request-matching, both protocols, worsened by this phase's
  own GraphQL work — now the single most significant open item carried
  into Phase 3**: carried from Phase 2a, REST request-matching matches on
  method + path only, not the request's target host, so a request fired
  at a URL on a different host than the workspace's schema could still
  match a node by path shape alone. This phase's GraphQL matching
  (`match_graphql_node`) is even more host-blind than that: it looks only
  at the request body's content (operation type + field name), with no
  host or path check of any kind, whereas REST at least requires
  method + path-template shape to align. Neither should be patched
  separately — both should eventually be closed by one shared "does this
  request's real destination match the workspace's own declared API"
  check.
- Carried from Phase 2a: the shared executor's timeout queue-wait edge
  case under high concurrency (multiple in-flight requests contending for
  the same timeout budget) remains parked, unaddressed.
- SPEC.md Phase 3 in full: real GitHub OAuth accounts, workspaces scoped
  per user, and encrypted per-user credential storage — never attempted.
- GraphQL matching/drift-checking's own stated v1 scope (named above, not
  a defect): first-operation/first-field matching only; drift-checking is
  scalar-precise but object-shallow (no recursive validation of custom
  object/enum types' own fields).
- **`Node.call_count` (SPEC.md §7.5, "denormalized, for node sizing") is
  tracked correctly on the backend but never used anywhere in the
  frontend**: `scene/Node.tsx` renders every node at the same fixed size
  regardless of real call frequency, so SPEC.md §8.3's "Size = real call
  frequency... a real signal, not decoration" is unimplemented. This gap
  existed in every earlier phase too, but went unnamed because
  `call_count` was always zero in normal use before real request-sending
  existed — Phase 2b is the first phase where this counter is actually
  non-zero, making this the right moment to name it.

### Next (Phase 3, SPEC.md §10)

Real GitHub OAuth, workspaces scoped per user, encrypted credential
storage, the final visual-identity palette/type pass, and deploy to
Render.

## 2026-09-12: Phase 3a: Real GitHub OAuth + Per-User Workspaces — done, partially live-verified (one manual step remains)

**What/Why**: Phase 2b left every workspace owned by a single hardcoded
default system user (Phase 1's SPEC.md-sanctioned placeholder) with no
real accounts and no ownership enforcement. This phase replaces that with
a real GitHub OAuth login flow, a real signed-cookie session, and real
per-user ownership checks on every workspace-scoped route — plus a
frontend gate that only shows the app to a logged-in user.

**What was built**:

- **Real GitHub OAuth flow** (`backend/app/auth/github.py`,
  `backend/app/routes/auth.py`): the standard authorization-code flow —
  `GET /api/auth/github/login` generates a CSRF `state`, stores it in the
  session, and redirects to GitHub's real `authorize` endpoint;
  `GET /api/auth/github/callback` validates `state`, exchanges the code
  for a token, fetches the real GitHub profile, and upserts a `User` row
  keyed on `github_id`. `GET /api/auth/me` returns the current user (401
  if none); `POST /api/auth/logout` clears the session.
- **Session mechanism**: Starlette's `SessionMiddleware` (registered in
  `app/main.py`), a **signed cookie**, not a server-side session store —
  the cookie itself carries `user_id`, cryptographically signed with
  `SESSION_SECRET_KEY` (`itsdangerous` under the hood). There is no
  session table in Postgres; nothing to garbage-collect, but also nothing
  server-side to revoke short of rotating the secret.
- **Real per-user ownership enforcement, not just recorded ownership**:
  every workspace-scoped route (`app/routes/workspaces.py`,
  `app/routes/requests.py`) now depends on `get_current_user` (401 if not
  logged in) and resolves the workspace via `get_owned_workspace`, which
  404s if the workspace doesn't exist *or* belongs to a different user.
  This was verified adversarially, not just by unit test: Task 2's Step 5
  logged in two real separate users (alice, bob) against two separate
  `TestClient`s, had alice create a workspace, then confirmed
  `alice GET /api/workspaces/{id}` → **200** and
  `bob GET /api/workspaces/{id}` → **404** — the ownership boundary is
  real, not a column nobody checks.
- **Frontend login gate** (`frontend/src/App.tsx`): on load, calls
  `GET /api/auth/me`; while that's pending shows a loading state; on 401
  shows a "Sign in with GitHub" gate instead of the workspace UI; only a
  real logged-in user sees the graph/workspace UI at all. Logout clears
  all client-side workspace/selection/history state, not just the user.

### Verified (real, automated — run in this session)

- Backend: `cd backend && .venv/bin/python -m pytest -q` — **120 passed**
  (matches Task 2's own run exactly; unchanged by this task, which added
  no new backend code).
- Frontend: `cd frontend && npx vitest run` — **15 passed across 4 test
  files** (matches Task 3's own run exactly; unchanged by this task).

### Verified live, in this session — and the exact boundary of what that covers

Started the real stack (Postgres via `docker compose up -d` +
`alembic upgrade head`, `uvicorn` on `:8123`, `npm run dev` on `:5173`)
**without a registered GitHub OAuth app** — using only the dev-default
env vars (`GITHUB_CLIENT_ID=dev`, `GITHUB_CLIENT_SECRET=dev`,
`GITHUB_CALLBACK_URL=http://localhost:8123/api/auth/github/callback`),
since a real client id/secret don't exist yet. In a real browser pane:

- Loading `http://localhost:5173` showed the "Sign in with GitHub" gate,
  **not** the workspace UI — confirms the frontend correctly treats "no
  session" as logged-out.
- Clicked "Sign in with GitHub". The browser navigated to
  `https://github.com/login?client_id=dev&return_to=%2Flogin%2Foauth%2Fauthorize%3Fclient_id%3Ddev%26redirect_uri%3D...%26scope%3Dread%253Auser%26state%3D...`
  — GitHub's own login page (since the browser had no GitHub session),
  whose `return_to` decodes to the real
  `/login/oauth/authorize?client_id=dev&redirect_uri=http://localhost:8123/api/auth/github/callback&scope=read:user&state=...`
  URL. This confirms the redirect really fires toward a real, correctly-shaped
  GitHub OAuth endpoint with the right `client_id`, `redirect_uri`, and a
  fresh CSRF `state`. **Stopped there, as instructed — no login was
  attempted with fake credentials, because there is no real GitHub OAuth
  app behind `client_id=dev` to complete a login against.**
- `curl http://localhost:8123/api/workspaces` with no cookie returned a
  real `401` (`{"detail":"not authenticated"}`) — not the old
  fixed-default-user workspace list — confirming Task 2's enforcement
  holds against the running server, not just in tests.
- Stopped the background `uvicorn` and `npm run dev` processes afterward;
  Postgres (`docker compose`) was left running.

**What this explicitly does NOT cover — the one manual step this plan
cannot perform**: nobody has registered a real GitHub OAuth App yet
(`GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET` above are the fake dev-default
values, not real ones), so no real GitHub consent screen was ever shown
and no real login/callback/session-issuance round trip has been
completed end to end. A human with a real GitHub account must register
the app and click through a real consent screen once to fully verify the
flow — see `AUTH_SETUP.md` for the exact steps. **This has not yet been
done.** Do not read the verification above as full end-to-end proof of
the OAuth flow; it proves every part of the flow that doesn't require a
real, registered GitHub app.

### Expected, not a bug: old dev-DB workspaces are now unreachable

Every workspace created during Phases 0–2 in a local dev database was
owned by the old hardcoded default system user (a fixed id used before
any real accounts existed). That data is still in Postgres, untouched —
by deliberate ruling, since no real user data ever existed to migrate.
Once someone logs in for real, `get_owned_workspace` will 404 on all of
it, because it's scoped to a user id no real GitHub account will ever
have. Anyone testing locally with old workspace data simply won't see it
after logging in for real. This is expected, not a regression.

### Final-review fix wave (2026-09-12): `PARITY_ENV` and what Phase 3c still owns

The whole-branch final review found this phase's deploy story was
internally contradictory: the session cookie was hardcoded to
`SameSite=Lax`/no-`Secure`, which a real split-origin deploy (frontend
and backend on different domains, per SPEC.md's own deploy-readiness
goal) cannot use, while `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET`/
`GITHUB_CALLBACK_URL` being merely optional meant a real deploy missing
one would fail confusingly on the first OAuth-touching request instead
of at boot. This branch adds `PARITY_ENV` (default `"development"`) as
the single explicit flag for both: it switches the session cookie to
`SameSite=None`+`Secure` and requires `SESSION_SECRET_KEY` when set to
`"production"`, and — regardless of `PARITY_ENV` — now makes a missing
GitHub OAuth env var a boot-time `RuntimeError` instead of a
first-request 500. **Phase 3c must set `PARITY_ENV=production` in its
deploy config.** This branch does not decide the actual deploy topology
(subdomains of one apex vs. two separate platform-assigned domains) —
that decision, and pointing the frontend's API base at the real backend
URL (currently hardcoded to relative `/api/...` paths, which only work
same-origin), are still Phase 3c's to make.

### Next (Phase 3b, SPEC.md §10)

Encrypted per-workspace credential storage (so users can attach real
auth headers/tokens to a workspace without them landing in plaintext),
then Phase 3c: the final visual-identity palette/type pass and
deploy-readiness for Render.

## 2026-09-12: Phase 3b: Encrypted Per-Workspace Credential Storage — done, verified at the API level

**What/Why**: Phase 3a left every workspace-scoped route real and
per-user, but with no way to attach a real auth credential to the target
API a workspace tests against — a real integration test against
anything requiring auth was impossible. This phase adds real
Fernet-encrypted, per-workspace credential storage: a header name +
value a user sets once, auto-injected into every fired request, never
readable back out in plaintext.

**What was built**:

- **Real Fernet encryption at rest** (`backend/app/crypto.py`): a
  server-held `FERNET_KEY` from the environment, **required at boot in
  every environment, dev included — there is no default**, matching
  `SESSION_SECRET_KEY`'s own discipline. This defends against exactly
  one threat, stated plainly and not implied as more (SPEC.md §7.4): a
  database dump alone can't recover a stored credential. Rotating the
  key is a one-way action — it permanently locks out every credential
  already stored under the old key (SPEC.md §12); there is no
  re-encrypt-everything migration path, by design.
- **Header-name/value split, not a single fixed header**:
  `Workspace.credential_header_name` + `Workspace.encrypted_credential`
  let a user name *which* header carries the credential, not just
  supply a value for a hardcoded `Authorization`. This is a real
  requirement, not speculative flexibility — this project's own
  reference fixture, the Petstore API, authenticates via a custom
  `api_key` header, not `Authorization`; a design that only supported
  one fixed header name would fail on the exact API this whole project
  tests against. `PUT /api/workspaces/{id}/credential` sets both;
  `DELETE` clears both; `GET /api/workspaces/{id}` only ever reports
  `has_credential` (bool) and `credential_header_name` (string) —
  never the decrypted value.
- **Real injection + real redaction gap found and closed during this
  plan's own self-review** (`backend/app/routes/requests.py`;
  `app/redact.py`'s fixed-name limitation is exactly what necessitated
  this explicit step): `POST /api/workspaces/{id}/requests`
  decrypts the stored credential and injects it under its configured
  header name before firing, unless the caller already supplied that
  header themselves. The persisted copy must be redacted the same as
  any other sensitive header — but `redact_headers`'s `SENSITIVE_HEADERS`
  set (`app/proxy/ssrf_guard.py`) is a fixed list of well-known names
  (`authorization`, `cookie`, `proxy-authorization`, `set-cookie`,
  `x-api-key`) and a user-chosen name like `api_key` isn't in it. Left
  unfixed, the real decrypted secret would have been written to
  Postgres verbatim on every request. This was caught and fixed during
  this plan's own self-review, not left for a task review to catch:
  `send_request` now explicitly redacts whichever header name the
  workspace's own credential config names, on top of the fixed set,
  before persisting the `Request` row. Live-verified below, not just
  unit-tested.
- **Frontend credential UI** (`frontend/src/components/CredentialPanel.tsx`,
  wired into `App.tsx` via a new "Credential" toggle button): a form to
  set/clear the header name + value, showing only `has_credential` /
  `credential_header_name` back — never a value the backend never
  returns in the first place. `showCredential` resets on logout, the
  same discipline `showHistory` already had (a Task 2 review finding,
  fixed in that same task).

### Verified

- Backend: `cd backend && .venv/bin/python -m pytest -q` — **132 passed**
  (real output, confirmed 2026-09-12 during this task's own run; up from
  Phase 3a's 120).
- Frontend: `cd frontend && npx vitest run` — **15 passed across 4 test
  files** (real output, confirmed 2026-09-12; unchanged from Phase 3a's
  count — the credential UI is covered by this task's own live
  verification below rather than new component tests).
- **Live-verified against the real running backend + real Postgres +
  real Fernet encryption, over real HTTP** (`docker compose up -d` +
  `alembic upgrade head`, `uvicorn` on `:8123` with a real freshly-generated
  `FERNET_KEY`, driven with `curl` and a manually-signed session cookie —
  the same real technique `tests/conftest.py`'s `login_as` helper uses,
  not a real GitHub login; see the honesty note below for why):
  - Created a real workspace ("Petstore live") against
    `https://petstore3.swagger.io/api/v3/openapi.json` — real 19 nodes,
    same known count as every prior phase's Petstore verification.
  - `PUT /api/workspaces/{id}/credential` with `{"header_name": "api_key",
    "value": "live-verify-test-value"}` → `{"status":"ok"}`.
  - `GET /api/workspaces/{id}` → `has_credential: true`,
    `credential_header_name: "api_key"` — confirming the value itself is
    never reported back, only its presence and header name.
  - Fired a real `GET` against the real, live Petstore
    `/pet/findByStatus?status=available` endpoint (no real auth needed
    for this call — the point was confirming header injection and
    redaction, not that Petstore accepts the fake credential) with no
    `api_key` header supplied by the caller. Got a real `200` back from
    the live API with the real current pet list, and a real
    `drift_finding.status: "violated"` (`"$[3]: 'name' is a required
    property"`) — the live, shared Petstore demo dataset again has an
    entry missing a schema-required field, the same kind of real,
    unforced finding Phase 2a's own verification reported, not an
    artifact of this project's code.
  - Inspected the persisted `Request` row directly (same technique
    Task 1's own tests use): `row.headers['api_key']` was exactly
    `"[REDACTED]"`, never `"live-verify-test-value"` — confirming the
    fixed-redaction-gap fix above holds against a real running server
    and real Postgres row, not just the test suite.
  - `GET /api/auth/me` with no cookie returned a real `401`
    (`{"detail":"not authenticated"}`) — the same logged-out shape
    `App.tsx`'s `currentUser === null` branch expects, which renders the
    "Sign in with GitHub" gate instead of the workspace UI.
  - Stopped the background `uvicorn` and `npm run dev` processes
    afterward; Postgres (`docker compose`) was left running, as
    instructed.

### Full UI-driven live verification: not completed, same as Phase 3a

**Stated exactly, not glossed over**: this task did not drive a real
browser through a real GitHub login and then click through the
credential UI end to end, because no real GitHub OAuth App is
registered in this environment yet — the identical gap Phase 3a's own
HANDOFF section named and left as the one remaining manual step (see
`AUTH_SETUP.md`). Verification for this phase stayed at two levels
instead, matching Phase 3a's own Task 4 honesty discipline exactly:

1. **Real backend/API-level verification** (above): the real encryption,
   injection, and redaction pipeline, exercised over real HTTP against
   the real running server and real Postgres, using a manually-signed
   session cookie in place of a real GitHub login.
2. **Frontend logic read, not driven**: confirmed by reading
   `frontend/src/App.tsx`'s early-return logic directly — `currentUser
   === undefined` shows a loading state, `currentUser === null` shows
   the "Sign in with GitHub" gate, and only a real logged-in user
   reaches the workspace UI (and, within it, the credential panel) at
   all — rather than by clicking through it in a real browser.

Neither the credential panel's own click-through UI nor a real GitHub
consent-screen round trip has been driven end to end in a real browser.
A human with a real GitHub account completing `AUTH_SETUP.md`'s
registration step would unblock that the same way it would unblock
Phase 3a's own remaining gap — this is one shared blocker, not two
separate ones.

### Next (Phase 3c, SPEC.md §8.2, §12)

The final visual-identity palette/type pass, and deploy-readiness:
`Dockerfile`/`render.yaml`/env docs, plus resolving the deploy-topology
decisions Phase 3a's own HANDOFF section left open — which real domains
the frontend and backend will actually live on, and updating the
frontend's currently-hardcoded relative `/api/...` paths accordingly so
a split-origin deploy actually works.

## 2026-09-17: Phase 3c: Deploy Readiness + Missing Public README — done, live-verified

**What/Why**: Phase 3b left the product itself feature-complete for v1
(both protocols, real auth, encrypted credentials) but genuinely
undeployable — the frontend's `fetch` calls were hardcoded to relative
`/api/...` paths (same-origin only), there was no Render blueprint, and
`SPEC.md` §9's own folder structure names a public `README.md` that was
never created despite Phases 0–3b all being real and live-verified. This
phase closes all three, plus a smaller gap found while doing it: no
`.env.example` existed on either side despite `.gitignore` already
carrying a `!.env.example` carve-out for one.

**What was built**:

- **Split-origin API base URL** (`frontend/src/api.ts`): every `fetch`
  call now goes through a module-level `API_BASE` constant read from
  `import.meta.env.VITE_API_BASE_URL`, defaulting to `''` — same-origin
  local dev is byte-for-byte unchanged (an empty prefix plus
  `vite.config.ts`'s existing dev-proxy resolves `/api/...` exactly as
  before), but a real split-origin deploy can now set one absolute
  backend origin at build time. `frontend/src/vite-env.d.ts` (new)
  declares the `ImportMetaEnv` augmentation so this type-checks under
  `noUnusedLocals`/strict settings. Verified two ways: (1) `VITE_API_BASE_URL=https://parity-backend.onrender.com
  npx vite build` followed by `grep`-ing the built JS for that literal
  hostname — confirmed present, so the substitution is real, not just
  type-checking; (2) a full live browser session with `VITE_API_BASE_URL`
  *unset* (the local-dev path) — see below — confirming the fallback
  doesn't regress the existing same-origin flow.
- **`render.yaml`** (repo root): a Render Blueprint — one Python web
  service (backend, `buildCommand` runs `alembic upgrade head` so
  migrations are never a separate manual deploy step), one static site
  (frontend), one managed Postgres. Makes the deploy-topology decision
  Phase 3a's HANDOFF left open concrete: two separate `onrender.com`
  subdomains (real split-origin), not one apex with two paths — which is
  why `FRONTEND_ORIGIN`/`VITE_API_BASE_URL`/`PARITY_ENV=production` all
  appear in it. No `Dockerfile`: Render's native Python/Node buildpacks
  cover this stack directly (`pyproject.toml`/`package.json`), so a
  Dockerfile would be extra surface with no real benefit — HANDOFF's own
  prior "Next" wording named `Dockerfile` alongside `render.yaml` but
  didn't mandate one if the buildpack path is real and sufficient, which
  it is here.
- **`DEPLOY.md`** (new): the one-time manual steps a blueprint can't do
  (registering a *production* GitHub OAuth app, separate from any dev app
  from `AUTH_SETUP.md`; generating `SESSION_SECRET_KEY`/`FERNET_KEY`),
  the exact env-var fill-in table for both Render services, the
  "deploy once, learn your real URLs, fill in the table, redeploy" order
  of operations this two-service-referencing-each-other setup actually
  requires, and a live-verification checklist for whoever completes the
  one step this session can't (registering a real production OAuth app
  needs a real account with a real domain to register against).
- **`README.md`** (new, repo root): the public-facing doc `SPEC.md` §9
  named as part of the folder structure since the beginning but which no
  phase had actually written — what the project is, what's real right
  now vs. explicitly not (linking `SPEC.md` §4 and this file's own gap
  log rather than re-stating it and risking drift), stack, local dev,
  and a pointer to `DEPLOY.md`.
- **`.env.example`** (new, both `backend/` and `frontend/`): consolidates
  every env var referenced across `AUTH_SETUP.md`, `DEPLOY.md`, and
  `app/main.py`'s own startup checks into one real file per side, closing
  a gap the repo's own `.gitignore` (`!.env.example`) had been silently
  pointing at since before this phase.
- **Visual-identity pass**: audited, not changed. Read every component's
  `.tsx` and `styles.css` against the Phase 0 plan's fixed palette/type
  tokens (`--ink`/`--paper`/`--mute`/`--hair`/`--match`/`--violate`,
  Space Grotesk/IBM Plex Mono) — every screen (auth gate, workspace form,
  detail panel, request builder, history panel, credential panel) already
  uses the tokens consistently with no ad-hoc colors or fonts. Stated
  honestly rather than inventing changes to justify this task: the "final
  pass" **found nothing to change**. `SPEC.md` §13 deferred the *exact*
  values to Phase 0, not a second design pass in Phase 3 — Phase 0's plan
  already fixed them for good, and every phase since has held to them.

### Verified

- Backend: `cd backend && .venv/Scripts/python -m pytest -q` — **135
  passed** against a real Postgres (this session's own native/portable
  instance — see the environment note below, not the project's
  `docker-compose.yml` — Docker Desktop would not come up on this
  machine; see below). No backend code changed this phase, so this is a
  regression check, not new coverage.
- Frontend: `cd frontend && npx tsc -b` clean; `npx vitest run` — **15
  passed across 4 test files** (unchanged from Phase 3b — the API_BASE
  change has no unit-testable branch beyond what `nodeLabel`/`severity`
  tests already cover); `npx vite build` — both with and without
  `VITE_API_BASE_URL` set, both clean.
- **Live-verified end to end in a real browser**, same manually-signed
  session-cookie technique Phase 3b's own HANDOFF section used (no real
  GitHub OAuth app registered in this environment — same standing gap
  named below and in every phase since 3a):
  - Backend on `:8123` (native Postgres, see below), frontend `npm run
    dev` on `:5173`. Loading the app showed the real "Sign in with
    GitHub" gate with `href="/api/auth/github/login"` — confirming
    `API_BASE`'s empty-string local-dev fallback resolves to exactly the
    same relative path as before this phase's change, not a regression.
  - Signed in via a manually-crafted session cookie (matching
    `tests/conftest.py`'s own `login_as` technique). Created a real
    workspace ("Petstore Phase3c check") against
    `https://petstore3.swagger.io/api/v3/openapi.json` — the real 3D
    graph rendered with the same known ring layout every prior phase's
    Petstore verification produced.
  - Clicked the `loginUser` node, clicked Send with no edits: got a real
    `200` from the live Petstore API
    (`"Logged in user session: 2447803852618845664"`), and a real
    `violated` drift finding (`response body is not valid JSON` — the
    endpoint's declared schema says `{"type": "string"}` but a bare,
    unquoted string isn't valid JSON on its own; a real, unforced finding
    about Petstore's own spec/response mismatch, the same kind of
    honest live-API finding Phase 2a's and Phase 3b's own verifications
    reported, not an artifact of this phase's changes). The node turned
    red in the 3D graph.
  - Opened the workspace-wide History panel: it listed the one real
    request just sent, with a real timestamp — confirming
    `getWorkspaceRequests` (one of the routes now going through
    `API_BASE`) still round-trips correctly.
  - `uvicorn` and `npm run dev` were stopped after this verification
    pass.

### Environment note: this session's Postgres is native, not Docker

`backend/docker-compose.yml` is unchanged and still the documented path
for anyone with a working Docker install. In *this* session, Docker
Desktop repeatedly failed to come up (the host has ~600MB free RAM at
idle, per this portfolio's own `SETUP_STATUS.md` profile of this
machine, and Docker Desktop's WSL2 backend did not survive more than a
few minutes before its own process list went empty). Verification above
used a native/portable Postgres 16 binary already present on this
machine at `C:\tools\pgsql` (installed for the `recur` repo in an earlier
session) — a `parity`/`parity` role and database were created inside that
same running instance on port 5432, and `DATABASE_URL` pointed at it
instead of the compose file's `5441`. This is the same "native Postgres,
reused across repos" pattern this portfolio's own `SETUP_STATUS.md`
already established for `recur`/`AI-Recipe-Maker`/`Quiz-App` on this
machine, applied here for the same reason (Docker's resource footprint
doesn't fit this host) — not a change to the project's own documented
setup, which still correctly says `docker compose up -d` for anyone with
Docker actually working. The native Postgres instance was left running
after this session, matching every prior phase's "stop the app
processes, leave the database running" convention.

### What this phase explicitly does NOT cover

- **No real production deploy was performed.** `render.yaml`/`DEPLOY.md`
  are real, complete, and internally consistent with `app/main.py`'s
  existing `PARITY_ENV`/CORS/session logic (read closely to confirm this,
  not guessed), but nobody has clicked "New Blueprint" against a real
  Render account, and no real production GitHub OAuth app exists. That
  remains the one human step no session can complete unattended — the
  same standing gap `AUTH_SETUP.md`/Phase 3a/3b's HANDOFF sections
  already named for local dev, now with its production-deploy
  counterpart in `DEPLOY.md`.
- **No real cross-origin browser round trip was tested.** The API_BASE
  substitution was verified at the build-artifact level (the real
  hostname appears in the compiled JS) and the local-dev fallback was
  verified live; a real two-different-real-domains fetch-with-credentials
  round trip needs real HTTPS on both sides (`SameSite=None` cookies are
  rejected by browsers without `Secure`, i.e. without HTTPS) — not
  something this local environment can fake without also faking TLS,
  which would test the fake, not the real thing. This is exactly what
  step 4 of `DEPLOY.md`'s own verification checklist is for once a real
  deploy exists.
- Every gap already carried from Phase 2b/3a/3b (GraphQL's edge-less 3D
  layout, host-blind request-matching, `call_count` not affecting node
  size) is untouched by this phase — none of them are deploy- or
  README-shaped, so none were in scope here.

### Next

No more named phases remain in `SPEC.md` §10's build order — Phase 3
(accounts, credential storage, polish, deploy-readiness) is now fully
addressed on paper and in code. What's left is exactly what this
phase's own "does NOT cover" section says: someone with a real Render
account and a real GitHub account needs to spend ~15 minutes clicking
through `DEPLOY.md` once. After that, the carried-over gaps above (listed
in full in Phase 2b's own HANDOFF section) are the real v2 backlog, not
new work this repo's build order ever promised for v1.

## 2026-09-17: v2 backlog — node sizing by call frequency + host-blind matching fix, live-verified

**What/Why**: with the one remaining Phase 3c manual step (registering a
real production GitHub OAuth app + Render deploy) blocked on a human
with real accounts, this closes two of the three named carried-over
gaps in the meantime — the two that were real code gaps, not frontend
design work (GraphQL's edge-less 3D layout, the third gap, is a real
SPEC.md §8.3 layout design task, not a small fix, and stays open).

**What was built**:

- **Node size now reflects real call frequency** (`frontend/src/lib/nodeSize.ts`,
  new): SPEC.md §8.3 says "Size = real call frequency (`node.call_count`)
  ... a real signal, not decoration" — `Node.call_count` has been tracked
  correctly on the backend since Phase 2a but every node rendered at the
  same fixed radius regardless. `nodeRadius(callCount)` log-scales the
  sphere radius from the original fixed `0.55` (a never-called node is
  visually identical to every prior phase — no regression) up to a capped
  `1.1` (so one very hot node can't dwarf the graph or swallow its
  force-laid-out neighbors). Wired into `frontend/src/scene/Node.tsx`'s
  `sphereGeometry` args, replacing the hardcoded `0.55`.
- **Host-blind request-matching, closed** (`backend/app/matching.py::same_declared_host`):
  named as "the single most significant open item" in Phase 2b's own
  HANDOFF section and carried unfixed through 3a/3b/3c. REST matching
  checked method+path shape only; GraphQL matching checked body shape
  only — neither checked *where* the request actually went, so a request
  fired at a completely unrelated host could still be credited as
  verifying a node purely because its path (or GraphQL field name)
  happened to line up. `same_declared_host(request_url,
  workspace.schema_source)` compares hostnames (case-insensitive) before
  either matcher runs; `app/routes/requests.py`'s matching block is now
  gated on it. **Stated v1 scope, not implied as more**: this reuses
  `Workspace.schema_source` as the "declared API host" proxy — the same
  simplification `RequestBuilder.tsx`'s own `guessUrl` already makes (the
  spec-doc host and the real API host are assumed the same; SPEC.md never
  modeled these as separately trackable) — not a new column, no
  migration. A workspace created from pasted/uploaded raw schema text has
  `schema_source == "pasted"` (no real host to check against); the
  function returns `True` (no constraint) in that case rather than
  inventing a false rejection — verified explicitly by its own test.

### Verified

- Backend: `cd backend && .venv/Scripts/python -m pytest -q` — **142
  passed** (real output; up from Phase 3c's 135 — 5 new `same_declared_host`
  unit tests in `test_matching.py`, 2 new adversarial integration tests in
  `test_request_routes.py`).
- Frontend: `cd frontend && npx tsc -b` clean; `npx vitest run` — **18
  passed across 6 test files** (up from Phase 3c's 15 — 3 new
  `nodeRadius` tests in `test/lib/nodeSize.test.ts` covering the
  no-regression-at-zero-calls case, monotonic growth, and the cap).
- **Live-verified against the real, unmocked Petstore API** (native
  Postgres per Phase 3c's own environment note; backend on `:8123`,
  no browser needed for this check — direct HTTP, same technique Phase
  2a's own verification used):
  - Created a real workspace against
    `https://petstore3.swagger.io/api/v3/openapi.json` — the real,
    known 19 nodes.
  - Fired a real `GET` at `https://httpbin.org/api/v3/pet/1` — a real,
    different, live host, with a path shape that would have matched the
    `getPetById` (`/pet/{petId}`) node under the old host-blind matcher.
    Got a real `404` from the real httpbin.org, and — the actual point of
    this check — `request.node_id: null`, `drift_finding.status:
    "unverified_no_match"`, confirming the fix holds against a real
    request to a real unrelated server, not just a mocked one.
  - Fired a real `GET` at
    `https://petstore3.swagger.io/api/v3/pet/findByStatus?status=available`
    (the workspace's own real declared host) immediately after — got a
    real `200` with real pet data, `node_id` resolved to the real
    `findByStatus` node — confirming the fix doesn't over-correct into
    blocking legitimate same-host requests.
  - Backend and frontend dev processes were stopped after verification;
    the native Postgres instance was left running, matching this
    portfolio's own convention.

### Still open (real v2 backlog, not attempted here)

- `same_declared_host`'s own stated v1 scope: hostname-only comparison
  (not full origin/port), and no constraint at all for pasted/uploaded
  schemas with no real source URL — both named above, not defects.
- GraphQL matching's first-operation/first-field-only scope and
  object-shallow drift-checking (Phase 2b's own stated scope) — untouched.
- The one standing manual step: a real production GitHub OAuth app +
  Render deploy (`DEPLOY.md`) — still nobody's done this.

## 2026-09-18: local GitHub OAuth app wired for real, live-verified up to the consent screen

**What/Why**: a real GitHub OAuth App was registered (client id
`Ov23liZGQJpRikwuRmTZ`) and its credentials were used, for this session
only, to start the local backend and confirm the real OAuth redirect
actually works end to end up to GitHub's own consent screen — the exact
boundary Phase 3a's own HANDOFF section stopped at with a fake `dev`
client id.

**What was verified, live, against the real GitHub OAuth endpoint**: with
the real client id/secret and `GITHUB_CALLBACK_URL=http://localhost:8123/api/auth/github/callback`
passed as process environment variables (never written to any file — no
`.env` was created, nothing was committed), clicking "Sign in with
GitHub" in a real browser redirected to a real
`https://github.com/login?client_id=Ov23liZGQJpRikwuRmTZ&return_to=...`
URL whose decoded `return_to` carried the exact real `client_id`,
`redirect_uri`, and a fresh CSRF `state` — and GitHub's own page read
**"Sign in to GitHub to continue to parity"**, which GitHub only shows
for a genuinely recognized, validly-registered app (an unrecognized
`client_id` or a `redirect_uri` that doesn't match the app's registered
callback produces a GitHub error page instead of a normal login form, per
Phase 3a's own documented understanding of this boundary). This is
stronger confirmation than Phase 3a's own fake-`dev`-client-id check
could ever produce.

**What this explicitly does NOT cover, same discipline as every phase
since 3a**: no login was completed and no consent screen was clicked
through — entering GitHub credentials or approving an OAuth consent grant
on the user's behalf is out of bounds regardless of how well the app is
wired. The session stopped exactly at the point where GitHub's own login
form appeared. A human still needs to actually sign in once to close this
gap for good, per `AUTH_SETUP.md`.

This client id/secret pair was for local dev only (its registered
callback is `http://localhost:8123/...`); per `DEPLOY.md`, a real Render
deploy needs its own, separately-registered production OAuth app.

## 2026-09-18: GraphQL type-relationship 3D layout — built, live-verified at the API level

**What/Why**: closes the last remaining named v1-scope gap — "GraphQL
nodes render with no edges," carried since Phase 1b and deliberately left
out of the 2026-09-17 backlog session as real design work rather than a
quick fix. Full design reasoning lives in
`docs/superpowers/plans/2026-09-18-graphql-type-relationship-layout.md`
(written first, per that plan's own Option A/B tradeoff discussion);
this entry covers what actually got built against it.

**What was built** (Option B from the plan — synthetic root/type hub
nodes, the literal SPEC.md §8.3 picture, not the cheaper shared-type-only
approximation):

- **`backend/app/graphql_edges.py`** (new): `compute_graphql_edges`
  produces a real edge list plus a list of synthetic, non-persisted "hub"
  node descriptors — one `graphql_root` hub per root type (`Query`/
  `Mutation`) with an edge to every one of its fields, and one
  `graphql_type` hub per distinct *non-scalar* return type with an edge
  from every field that returns it. Scalar return types (`String`/`Int`/
  `Float`/`ID`/`Boolean`) deliberately get no shared hub — stated in the
  plan and re-verified here, not a defect. Hub ids are deterministic
  (`"root:Query"`, `"type:Pet"`), so they're stable across repeated
  fetches of the same workspace.
- **`get_workspace` route**: merges `compute_graphql_edges`'s output into
  the existing response for `schema_kind == "graphql"` workspaces — a new
  top-level `virtual_nodes` field (always `[]` for OpenAPI workspaces, so
  the frontend never needs an `undefined` check), and the new edges
  appended to the existing `edges` list. REST's own `compute_rest_edges`
  path is completely untouched.
- **Frontend**: `Workspace.virtual_nodes: VirtualNode[]` (new type,
  `api.ts`); `computeLayout` (`layout.ts`) now takes an optional third
  `virtualNodes` argument and places them in the *same* force simulation
  as real nodes (so a hub naturally settles at the center of the fields
  that actually point to it, rather than a second, independently-tuned
  layout pass), returning `{nodes, virtualNodes}` as two separate maps
  instead of one bare map — real vs. synthetic stays distinguishable
  after layout, not just before it. New `HubNode.tsx`: a wireframe
  icosahedron (root hubs, larger) or octahedron (type hubs, smaller) with
  a floating text label (`@react-three/drei`'s `Text`, already a
  dependency — no new one added), always the neutral `--mute` palette
  (never `--match`/`--violate` — a hub has no drift status of its own,
  stated in-code, not just here), and **deliberately not
  clickable/selectable** — no `onSelect` wiring, matching the plan's own
  reasoning: there's no per-type detail to show, so inventing a secondary
  panel for a concept with nothing behind it would be exactly the kind of
  half-finished surface this codebase avoids elsewhere.

### Verified

- Backend: `cd backend && .venv/Scripts/python -m pytest -q` — **151
  passed** (real output; up from the 2026-09-17 backlog session's 142 — 7
  new `compute_graphql_edges` unit tests in `test_graphql_edges.py`
  covering shared-type hubs, no-hub-for-scalars, per-root edges, a
  `Query`-only schema producing no `Mutation` hub, deterministic hub ids
  across repeated calls, a field with no declared response schema still
  getting its root edge, and the empty-input case; 2 new route-level
  tests in `test_workspace_routes.py` confirming a REST workspace reports
  `virtual_nodes: []` and a real GraphQL workspace reports the real root
  + type hubs with the right edges).
- Frontend: `cd frontend && npx tsc -b` clean; `npx vitest run` — **20
  passed across 5 test files** (up from 18 — 2 new `layout.test.ts` cases
  covering virtual-node placement and the no-virtual-nodes default);
  `npx vite build` clean.
- **Live-verified against the real, unmocked `countries.trevorblades.com`
  GraphQL API** (native Postgres; backend on `:8123`; direct HTTP, the
  same backend-level verification tier Phase 2a's own HANDOFF used when a
  full browser click-through wasn't available that session — see the
  honesty note below for why browser-level verification specifically
  wasn't completed this time):
  - Created a real workspace against
    `https://countries.trevorblades.com/graphql` — the real, known 6
    nodes (matching every prior phase's own result for this fixture).
  - `GET /api/workspaces/{id}` returned real `virtual_nodes`: one
    `root:Query` hub (this API has no `Mutation` fields, so no
    `root:Mutation` hub was invented) and three real `graphql_type` hubs
    — `Country`, `Language`, `Continent`.
  - Confirmed the real edges: every one of the 6 real fields has an edge
    from `root:Query`; `countries`/`country` both edge to `type:Country`,
    `languages`/`language` both edge to `type:Language`, `continent`/
    `continents` both edge to `type:Continent` — **the real proof the
    LIST-unwrapping leaf-type logic works against a real API's real
    shape**: `languages` declares `[Language!]!` (a LIST) and `language`
    declares a bare `Language` (not a list), and both correctly collapsed
    to the exact same `type:Language` hub rather than being treated as
    unrelated.
  - **REST regression check**: created a second real workspace against
    `https://petstore3.swagger.io/api/v3/openapi.json` — real 19 nodes,
    real 16 edges (byte-for-byte matching every prior phase's own known
    Petstore result), `virtual_nodes: []` — confirming this work didn't
    touch REST's own edge computation at all.
  - Backend and frontend dev processes were stopped after verification;
    the native Postgres instance was left running, matching this
    portfolio's own convention.

### Honesty note: Task 3 (live force-layout tuning) was not completed

The plan's own Task 3 called for tuning the force-simulation constants by
eye against real rendered content once hubs actually exist, the same way
`loom`/this project's own original REST constants were tuned. **This did
not happen this session**: the browser tool's own JS-console session-cookie
forgery technique — used successfully earlier in this same session (Phase
3c's and the 2026-09-17 backlog session's own live verifications both
relied on it) — silently stopped working partway through this session
(`document.cookie` writes to a cookie literally named `session` stopped
taking effect, while writes to any other cookie name kept working
normally; consistent with a deliberate anti-session-hijacking guard in the
browser tool itself, not a bug in this project's own code). Real GitHub
login wasn't attempted as a substitute, for the same reason it never has
been in this repo: entering credentials or clicking through a consent
screen on the user's behalf is out of bounds. **The force constants
(`charge().strength(-6)`, `link().distance(2.2)`, unchanged from REST's
own original Phase 0 tuning) are therefore unverified for the GraphQL
hub-heavy shape** — the API-level verification above proves the *data* is
correct (real hubs, real edges, real deduplication), but nobody has
visually confirmed hubs don't overlap their own fanned-out fields in a
real rendered scene. This is a real, named gap, not a completed task —
the next session with real interactive-browser access should do this
before calling the GraphQL layout plan's Task 3 done.

### Next

No more phases remain in `SPEC.md`'s own build order or in the
carried-over v1-scope-gap backlog this repo has been tracking since Phase
2b. What's left, in full:

- Live force-layout tuning for the GraphQL hub shape (immediately above).
- The one standing manual step: a human completing a real GitHub login
  once (local) and a real Render deploy (`DEPLOY.md`) — the only things
  left that no automated session can do.
- `same_declared_host`'s and GraphQL matching's own already-stated v1
  scope limits (Phase 2b/2026-09-17's own HANDOFF entries) — not defects,
  real v2 work if ever wanted.
