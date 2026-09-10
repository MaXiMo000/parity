# parity — SPEC v1

**Read this file first, in full, before writing any code.** It is written to
be self-contained: everything a fresh agent needs to start building is here.
If something is genuinely ambiguous after reading this whole document, say
so and propose a default rather than blocking — see §13.

---

## 1. What this is, in one line

**parity is a real API client that checks every request you send against
the API's own declared contract — its OpenAPI or GraphQL schema — live,
and renders the whole API surface as an explorable 3D map colored by
*verified*, not just *declared*.**

Give it a schema (an OpenAPI URL/file, or a GraphQL endpoint/SDL) and it
builds a 3D graph of every endpoint or type. Paste a `curl` command or
build a request by hand, hit send, and the backend proxies it to the real
server, gets the real response, and checks it against what that node's
schema actually promised. The node lights up green if reality matched the
contract, orange if it didn't — and every check is written to history, so
an endpoint's "has this ever broken its own contract" record accumulates
from real use.

## 2. Why this, why now

Two real gaps, not an invented need:

1. **No API client checks live behavior against the declared contract.**
   Postman, Insomnia, Hoppscotch, Bruno all let you browse a schema *and*
   let you send requests — but never connect the two. A response can
   silently violate its own OpenAPI/GraphQL contract (a field goes
   nullable, a status code changes, a type narrows) and nothing in any of
   these tools tells you. This is a real, common failure mode: the schema
   is the one artifact that's supposed to be a promise, and nobody checks
   whether the promise still holds.
2. **No API client has invested in the interface.** Every tool in this
   space is a form over a list — utilitarian by design, never by choice.
   API tooling is a real, currently-monetized category (Postman alone is
   a multi-billion-dollar company) — this isn't a market that doesn't
   exist, it's one where nobody has tried to make the interface actually
   good.

## 3. Scope decisions for v1 (each with its reasoning)

| Decision | Choice | Why |
|---|---|---|
| Protocols | **OpenAPI 3.x (REST) and GraphQL, both from day one** | A deliberate, larger-scope call (not the smaller "one ecosystem first" default) — the two protocols have genuinely different graph shapes (endpoints vs. types/fields) and proving the visual language works for both is part of the point. |
| Request input | **Curl-paste (fast path) and a real request builder (method/url/headers/body/auth)** | Curl-paste is the on-ramp — copy a request straight out of browser devtools or an existing script. The builder is for constructing one from scratch, or editing a parsed curl before sending. Both parse to the same internal request shape; there is one code path, not two. |
| Request execution | **Server-side proxy**, never a browser `fetch` | The target API's CORS policy is irrelevant to a tool testing *someone else's* API — a browser-side request would be blocked by CORS on most real APIs. The backend fires the real request and returns the real response to the frontend. This also means the backend owns SSRF protection (§7.3) — a real security boundary, not a nice-to-have. |
| Persistence | **Postgres, everything real from Phase 1** | Same call loom already made: the product's value is in real accumulated history (which endpoint broke its contract, and when), which only exists if every request/response/finding is actually stored, not held in memory for one session. |
| Auth | **Real accounts, GitHub OAuth** | Target-API credentials (a user's own API keys/tokens for the APIs they test) are real secrets that need to live somewhere scoped to one person — this is the same "stores something sensitive" shape `recur` already has (real accounts), not `loom`'s (no auth, nothing personal stored). GitHub OAuth over email/password: the target audience already has GitHub accounts, and it avoids building password-reset/email-verification infrastructure for a v1 — a real, deliberate scope cut, not laziness (email/password is real, sized v2 work if ever needed). |
| Credential storage | **Encrypted at rest** (Fernet symmetric encryption, server-held key) | Honestly scoped: this defends against a database dump, not a full secrets-manager/HSM setup. Stated here plainly, the same way `witness`/`portable` state their own real limits in their own READMEs rather than implying more rigor than exists. |
| Hosting | **Render**, matching `recur`/`LabLedger`/`loom` | No new infra decision to make — this portfolio's own precedent. |
| Visual identity | **A new, standalone palette and type system** — same procedural-only, no-imported-mesh discipline as the portfolio and `loom`, but its own colors and fonts | Explicit choice: this is a standalone flagship, not a sibling site. It should read as its own thing on sight, while holding the same craft bar. |

## 4. What v1 explicitly does NOT do (state it, don't silently skip it)

- **No schema inference from traffic alone.** If you have no OpenAPI/GraphQL
  source, parity has nothing to check a response against — every node is
  honestly `unverified: no schema`. Inferring a de-facto schema from
  observed traffic is a real, different, harder problem (and a genuinely
  good v2 idea) — not attempted here.
- **No mock servers.** parity checks real APIs; it doesn't stand one up.
- **No load/performance testing.** A different tool's job.
- **No CI integration** (a "run this collection on every PR" runner, the
  way Postman's Newman does). Real, sized v2 work.
- **No team/org sharing.** Workspaces are single-user in v1. Multi-user
  sharing with roles is a real feature on its own, not a corner to cut
  into v1.
- **No full OAuth2 authorization-code flow automation for target APIs.**
  You paste a token/key you already have; parity doesn't drive an OAuth
  dance on your behalf to obtain one. Real, sized v2 work (Postman's own
  OAuth2 helper is the precedent for how much surface that actually is).
- **HTTP(S) request/response APIs only.** No WebSockets, no webhooks, no
  gRPC. A different transport shape each, not attempted here.

## 5. Architecture overview

```
                    ┌──────────────────────────────┐
                    │   Browser (React + R3F)       │
                    │  3D graph · request builder ·  │
                    │  curl-paste · detail panel      │
                    └────────────┬──────────────────┘
                                 │ REST (synchronous — a single request/
                                 │ response round trip, no polling; this
                                 │ isn't a multi-minute background job the
                                 │ way a loom scan is)
                    ┌────────────▼──────────────────┐
                    │   FastAPI backend               │
                    │  ┌───────────────────────────┐ │
                    │  │ schema ingestion            │ │   parses:
                    │  │ (OpenAPI + GraphQL)          │─┼──▶ openapi-spec-validator
                    │  └───────────┬───────────────┘ │─┼──▶ graphql-core
                    │              │ builds Node rows │
                    │  ┌───────────▼───────────────┐ │
                    │  │ curl parser                 │ │
                    │  └───────────┬───────────────┘ │
                    │  ┌───────────▼───────────────┐ │   fires the real
                    │  │ request proxy                │─┼──▶ request, to the
                    │  │ (SSRF-guarded, §7.3)         │ │   real target server
                    │  └───────────┬───────────────┘ │
                    │  ┌───────────▼───────────────┐ │
                    │  │ drift validation             │ │   real response vs.
                    │  │ (match response → node,      │ │   that node's own
                    │  │  validate against schema)     │ │   declared schema
                    │  └───────────┬───────────────┘ │
                    │  ┌───────────▼───────────────┐ │
                    │  │ auth (GitHub OAuth)          │ │
                    │  └───────────────────────────┘ │
                    └────────────┬──────────────────┘
                                 │
                          ┌──────▼──────┐
                          │  Postgres   │
                          │  users, workspaces, nodes,
                          │  requests, responses,
                          │  drift_findings
                          └─────────────┘
```

## 6. Data flow: from "give it a schema" to "watch a node light up"

1. User creates a workspace, gives it a schema source: an OpenAPI URL or
   uploaded file, or a GraphQL endpoint (introspected live) or SDL file.
2. Backend parses it into `Node` rows — one per REST operation
   (method + path template) or GraphQL field (type + field name) — each
   carrying its own declared request/response shape. Every node starts
   `unverified: never tested`.
3. Frontend renders the 3D graph from those nodes immediately — this is
   real before a single request has ever been sent.
4. User pastes a `curl` command (parsed server-side into a structured
   request, returned to the frontend for review/edit before sending) or
   builds one directly, and hits Send.
5. Backend validates the target URL isn't an SSRF target (§7.3), fires the
   real request to the real server, captures the real response.
6. Backend matches the request to a `Node`: REST by method + path-template
   match (`/users/{id}` matches a real call to `/users/123`); GraphQL by
   operation/selected-field name. A request matching no known node is
   still recorded (so it's visible in history) but produces
   `unverified: not in schema` rather than a guessed result.
7. Backend validates the real response against that node's declared
   schema — a real JSON Schema check derived from the OpenAPI response
   object, or a real type-shape check against the GraphQL field's declared
   type (nullability, scalar/object shape). Writes `Request`, `Response`,
   and `DriftFinding` rows.
8. The API call that sent the request returns the enriched result
   synchronously — no polling loop, this is a single interactive round
   trip, not a background job. The frontend updates that node's color and
   the detail panel immediately.

## 7. Backend

### 7.1 Stack

- **FastAPI** (async), **SQLAlchemy 2.x** + **Alembic**, **Postgres** —
  same stack as `loom`, no new infra decision to make.
- **httpx** for the real outbound proxy client.
- **openapi-spec-validator** + **jsonschema** for real OpenAPI parsing and
  response validation — established libraries, not a hand-rolled OpenAPI
  parser (a full OpenAPI 3.x parser is a large, well-solved problem; this
  is the "already-installed dependency solves it" rung of the ladder).
- **graphql-core** — the real reference GraphQL implementation in Python,
  for introspection, SDL parsing, and validating a real response's shape
  against a field's declared type.
- **A curl parser**: try the existing `uncurl` package first (parses a
  curl command into a structured request) — if it proves inadequate for
  the common flag set parity actually needs (`-X`/`--request`,
  `-H`/`--header`, `-d`/`--data`/`--data-raw`, `-u`/`--user`, `-G`,
  `-b`/`--cookie`), fall back to a small hand-rolled parser over
  `shlex.split` covering exactly those flags — confirm which during Phase
  2 (§13).

### 7.2 The two schema parsers, exactly what each produces

1. **OpenAPI**: fetched (URL) or uploaded (file), parsed with
   `openapi-spec-validator` (which also validates the spec is
   well-formed — a malformed spec fails the ingestion honestly rather
   than producing a half-built graph). One `Node` per
   `(method, path template)` operation, carrying its `operationId`, its
   declared request body schema (if any), and its declared response
   schemas keyed by status code.
2. **GraphQL**: either a live introspection query against the given
   endpoint, or a parsed SDL file, via `graphql-core`. One `Node` per
   field reachable from `Query`/`Mutation`/`Subscription` (v1: Query and
   Mutation only — Subscription is a different, streaming transport
   shape, out of scope per §4), carrying its declared argument types and
   return type (including nullability).

### 7.3 Request proxy safety — SSRF is a real, non-optional boundary

**The backend fires arbitrary HTTP requests to whatever URL a user gives
it. This is a textbook SSRF surface**, the same category of risk `loom`'s
Phase 2 named explicitly for its own sandboxed subprocess: a user (or a
malicious one) could point a request at `169.254.169.254` (the cloud
metadata endpoint most providers expose), `127.0.0.1`/`localhost`, or an
internal RFC1918 address, and use parity's own backend as a stepping stone
into infrastructure it was never meant to reach. This gets real mitigation
from the moment request-firing exists (Phase 2, §10) — not bolted on
after, not deferred, since there's no honest degraded state for "we proxy
requests but don't check where":

- Resolve the target hostname and reject the request before firing if the
  resolved IP is loopback, link-local, or any RFC1918 private range.
- Reject explicit `localhost`/`127.0.0.1`/`0.0.0.0`/`::1` by hostname too,
  not only by resolved IP (a naive check that only inspects the literal
  hostname is exactly the gap a redirect or a DNS trick exploits).
- A hard wall-clock timeout on every proxied request — a target that
  never responds must not hang the request indefinitely.
- Follow redirects manually (not via httpx's automatic follow) so every
  hop gets the same IP-range check — an initial safe URL that redirects
  to an internal address is the same class of bypass `carabiner`'s own
  README discipline would flag.

This gets its own adversarial test once Phase 2 is built (§11), the same
"prove the boundary actually holds" discipline `loom`'s drift-sandbox
adversarial pass already modeled in this portfolio.

### 7.4 Auth and credential storage

GitHub OAuth (the standard authorization-code flow) for real accounts.
Target-API credentials a user stores for a workspace (an API key, a
bearer token) are encrypted at rest with Fernet (symmetric, from the
`cryptography` package), keyed by a server-held secret from the
environment — this defends against a database dump, not a full
secrets-manager setup, stated plainly rather than implied as more than it
is.

### 7.5 Data model (Postgres, via SQLAlchemy)

```
user
  id            uuid pk
  github_id     text unique
  username      text
  created_at    timestamptz

workspace
  id                 uuid pk
  user_id            uuid fk -> user
  name               text
  schema_kind        text   # "openapi" | "graphql"
  schema_source      text   # the URL, or "uploaded"/"introspected"
  raw_schema         jsonb  # the parsed spec/SDL, kept for re-diffing on refresh
  encrypted_credential bytea nullable  # Fernet-encrypted target-API secret
  created_at         timestamptz
  updated_at         timestamptz

node
  id                     uuid pk
  workspace_id           uuid fk -> workspace
  kind                   text   # "rest_operation" | "graphql_field"
  method                 text nullable   # REST only
  path_template          text nullable   # REST only, e.g. "/users/{id}"
  operation_id           text nullable   # REST only
  type_name              text nullable   # GraphQL only, e.g. "Query"
  field_name             text nullable   # GraphQL only
  declared_request_schema  jsonb nullable
  declared_response_schema jsonb nullable
  call_count             int default 0  # denormalized, for node sizing

request
  id            uuid pk
  workspace_id  uuid fk -> workspace
  node_id       uuid fk -> node, nullable  # null if it matched no known node
  method        text
  url           text
  headers       jsonb   # redacted before persisting, same discipline as
                          # loom's carabiner/lockstep subprocess redaction
  body          text nullable
  sent_at       timestamptz

response
  id            uuid pk
  request_id    uuid fk -> request
  status_code   int
  headers       jsonb
  body          text nullable
  latency_ms    int
  received_at   timestamptz

drift_finding
  id            uuid pk
  response_id   uuid fk -> response
  node_id       uuid fk -> node, nullable
  status        text   # "matched" | "violated" | "unverified_no_schema" | "unverified_no_match"
  detail        text nullable   # the real diff: which field, what was declared vs. what came back
  created_at    timestamptz
```

### 7.6 API endpoints (v1)

```
GET    /api/auth/github/login       -> redirects to GitHub's OAuth consent
GET    /api/auth/github/callback    -> completes the flow, sets a session
GET    /api/auth/me                 -> the current user, or 401
POST   /api/auth/logout

POST   /api/workspaces                      {name, schema_kind, schema_source}
GET    /api/workspaces                      -> this user's workspaces
GET    /api/workspaces/{id}                 -> full graph: nodes + summary
POST   /api/workspaces/{id}/refresh-schema  -> re-fetch/re-parse, diff node set

POST   /api/curl-parse                      {curl: string} -> structured request
                                             (no side effects — just parses)

POST   /api/workspaces/{id}/requests        {method, url, headers, body}
                                             -> fires the real request, returns
                                                {request, response, drift_finding}
GET    /api/workspaces/{id}/requests        -> real request history
GET    /api/workspaces/{id}/nodes/{node_id}/history
                                             -> that node's drift findings over time
                                                (the same "did this regress" story
                                                loom's /diff endpoint tells for a
                                                whole graph, told here per-node)
```

## 8. Frontend

### 8.1 Stack

Vite + React + TypeScript, **React Three Fiber** + **three.js** for the 3D
graph, plain CSS — same restraint the portfolio family already holds
itself to, applied to a new, standalone design system (§8.2).

### 8.2 Visual design system — new, standalone, same discipline

**Not** the portfolio's or `loom`'s palette/type tokens — this is its own
flagship. What *is* non-negotiable, the same way it was for `loom`:
procedurally generated primitives only, no imported/modeled 3D assets. A
dark-mode-first base, one real "verified/matched" color and one real
"violated" color (the functional pair every node's state actually needs),
monospace for technical values (status codes, paths, field names) — the
same "measured value gets a measured typeface" idea the whole portfolio
already holds. **The exact palette and type choices are a real Phase 0
decision** (§13) — deferred the same way `loom` deferred its exact
force-layout constants: right the first time only once real content is
actually rendered in front of it, not decided in the abstract here.

### 8.3 The 3D graph itself

Dual-mode, sharing one visual language:

- **REST mode**: a tree/force-graph by path and tag — `/users`,
  `/users/{id}`, `/users/{id}/posts` read as a real hierarchy, the way a
  file tree does.
- **GraphQL mode**: a graph by type relationships — `Query` and
  `Mutation` as roots, fields fanning out to the types they return.
- **Color** = drift status: never-tested / matched / violated (the
  functional pair from §8.2, plus a neutral for never-tested).
- **Size** = real call frequency (`node.call_count`) — a node that's
  actually been exercised a lot is visibly more load-bearing than one
  nobody's ever called, a real signal, not decoration (same principle
  `loom`'s "size ∝ dependency count" already used).
- **Interaction**: orbit controls, click a node → detail panel (its
  declared schema, its real call history, the real request/response body
  of its most recent check, and the real diff if it's currently
  `violated` — "the receipt, not a claim," the same idea `loom`'s and the
  portfolio's own detail panels already state explicitly in their own
  code comments).

### 8.4 Non-3D chrome

- A request builder panel: method, URL, headers, body, a curl-paste
  toggle that parses into the same form fields for review before sending.
- A workspace switcher (a user's own workspaces, create-new affordance).
- A history view: every real request sent in this workspace, filterable
  by node.
- The node detail panel (§8.3) is the primary "why is this colored this
  way" surface, matching `loom`'s own detail-panel philosophy exactly.

## 9. Folder structure

```
parity/
├── SPEC.md
├── HANDOFF.md                  # created on first real progress
├── README.md                   # public-facing, written once Phase 1 is real
├── LICENSE
├── .gitignore
├── .github/workflows/ci.yml
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── models.py            # user/workspace/node/request/response/drift_finding
│   │   ├── db.py
│   │   ├── auth/
│   │   │   └── github.py        # OAuth flow
│   │   ├── routes/
│   │   │   ├── auth.py
│   │   │   └── workspaces.py
│   │   ├── schema/
│   │   │   ├── openapi.py       # parse -> Node rows
│   │   │   └── graphql.py       # introspect/parse SDL -> Node rows
│   │   ├── proxy/
│   │   │   ├── curl_parser.py
│   │   │   ├── ssrf_guard.py    # §7.3 — its own module, its own tests
│   │   │   └── client.py        # the real outbound httpx proxy
│   │   ├── drift/
│   │   │   ├── rest.py          # response vs. OpenAPI response schema
│   │   │   └── graphql.py       # response vs. GraphQL field type
│   │   └── crypto.py            # Fernet encrypt/decrypt for stored credentials
│   └── tests/
│       ├── test_openapi_schema.py   # real, small public OpenAPI specs
│       ├── test_graphql_schema.py   # real, small public GraphQL APIs
│       ├── test_curl_parser.py
│       ├── test_ssrf_guard.py       # the adversarial pass, §11
│       ├── test_drift_rest.py
│       ├── test_drift_graphql.py
│       └── test_routes.py
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── src/
    │   ├── main.tsx
    │   ├── App.tsx
    │   ├── styles.css            # the new, standalone design tokens (§8.2)
    │   ├── api.ts
    │   ├── scene/
    │   │   ├── Graph.tsx
    │   │   ├── Node.tsx
    │   │   └── Edge.tsx
    │   ├── components/
    │   │   ├── RequestBuilder.tsx
    │   │   ├── WorkspaceSwitcher.tsx
    │   │   ├── HistoryView.tsx
    │   │   └── DetailPanel.tsx
    │   └── lib/
    │       └── mode.ts           # same STILL/prefers-reduced-motion pattern
```

## 10. Phased build order

**Phase 0 — walking skeleton.** A hand-written fixture workspace (a small,
realistic OpenAPI-shaped graph — a handful of nodes) served by the real
FastAPI routes, no real parsing or proxying yet. A "send request" action
that returns a canned, fake result. **Goal: see a real, walkable,
correctly-styled 3D graph with a working click → detail → (fake) send
loop before any real parsing/proxying exists** — the same discipline
`loom`'s own Phase 0 already modeled for this portfolio.

**Phase 1 — real schema ingestion, real persistence.** Real OpenAPI
parsing (URL + file), real GraphQL introspection + SDL parsing, real
Postgres persistence of workspaces/nodes. No OAuth yet — `workspace.user_id`
(§7.5) is real and non-nullable from its first migration, but Phase 1
creates one real system/default `user` row that every workspace belongs to
until Phase 3's real GitHub OAuth replaces that with real per-person
accounts (a real migration reassigning ownership, not a schema change from
nullable to non-nullable after the fact — decide the exact reassignment
approach against real Phase-1 data once Phase 3 starts, not in the
abstract here). This proves the real data pipeline before adding anything
auth-shaped, the same way `loom` did. No request-firing yet; every node
stays honestly `unverified`.

**Phase 2 — real request execution and drift checking.** The real curl
parser, the real SSRF-guarded proxy (§7.3 — built in from the start of
this phase, not after), real drift validation for both protocols. This is
where the actual product value becomes real. Gets its own adversarial
test (§11) before being called done, the same way `loom`'s sandboxed
drift signal did.

**Phase 3 — accounts, credential storage, polish, deploy.** Real GitHub
OAuth, workspaces scoped per user, encrypted credential storage, the new
visual identity's final palette/type pass, deploy to Render.

## 11. Testing & verification discipline

Same bar every repo in this portfolio already holds itself to:

- **Real fixtures, not synthetic specs.** A real, small, public OpenAPI
  spec (e.g. a well-known small public API's own published spec) and a
  real, small, public GraphQL API (e.g. a public, no-auth GraphQL
  endpoint commonly used for exactly this kind of testing) — committed as
  real recorded fixtures, the same discipline `loom`'s own recorded
  PyPI/OSV fixtures already modeled.
- **Live-verify the whole pipeline against a real API** before calling
  any phase done — give it a real public API's real schema, send a real
  request, confirm a real drift finding (or a real "matched") comes back.
- **The SSRF boundary gets its own explicit adversarial test** once Phase
  2 is built: attempt a request at `127.0.0.1`, `169.254.169.254`, and an
  RFC1918 address, and confirm each is refused before ever reaching
  `httpx` — `loom`'s own drift-sandbox adversarial pass is the direct
  precedent for this discipline.
- **The curl parser gets tested against real curl commands** copied from
  real browser devtools output, not hand-typed minimal examples — the
  same "test against the real shape, not a guessed one" lesson `lockstep`
  and `loom` both already learned the hard way about lockfile parsing.

## 12. Deployment

Render, matching `recur`/`LabLedger`/`loom`: a web service for the FastAPI
backend, a static site for the Vite build, a managed Postgres instance.
Environment variables for the DB URL, GitHub OAuth client id/secret, and
the Fernet encryption key (generated once, never rotated casually — a
rotation invalidates every already-stored credential, worth a real
migration plan if it's ever needed, not attempted here).

## 13. Open questions / decisions deliberately left to the building agent

- **Exact palette and type choices for the new standalone visual
  identity** (§8.2) — can't be right until real content is actually
  rendered in front of it, the same reasoning `loom` used for its own
  force-layout tuning. Decide during Phase 0.
- **Curl parser: `uncurl` vs. hand-rolled** (§7.1) — try the existing
  library first: use it if it covers parity's actual real-world curl
  inputs correctly; fall back to a small hand-rolled parser over
  `shlex.split` for the specific flag set parity needs if it doesn't.
  Decide during Phase 2, against real pasted curl commands.
- **REST path-template matching algorithm** — matching a real incoming
  URL against a set of declared OpenAPI path templates
  (`/users/{id}/posts/{postId}`) needs real, correct precedence handling
  (a literal segment should win over a templated one at the same
  position). Confirm the exact approach against real OpenAPI specs during
  Phase 1, rather than trusting a remembered regex scheme.
- **GraphQL response validation depth** — whether to lean on
  `graphql-core`'s own execution-result validation machinery directly, or
  write a lighter custom shape-check against selected fields' declared
  types. Decide once real GraphQL fixtures are in front of it (Phase 2).

---

*Written 2026-09-10, as a new, standalone flagship — not a sibling of the
`/Users/ritis/Documents/Personal/` "Evidence, Not Claims" portfolio's own
family of repos, though it holds itself to the same process discipline:
git identity per repo, live-verification over unit-tests-alone, an honest
three-state model (`matched`/`violated`/`unverified` — never a blended
score), and redaction discipline for anything that touches real secrets.*
