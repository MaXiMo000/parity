# parity

A real API client that checks every request you send against the API's
own declared contract — its OpenAPI or GraphQL schema — live, and
renders the whole API surface as an explorable 3D map colored by
*verified*, not just *declared*.

Give it a schema (an OpenAPI URL, or a GraphQL endpoint) and it builds a
3D graph of every endpoint or field. Paste a `curl` command or build a
request by hand, hit send, and the backend proxies it to the real
server, gets the real response, and checks it against what that node's
schema actually promised. A node turns green if reality matched the
contract, red if it didn't — and every check is written to history, so
an endpoint's "has this ever broken its own contract" record accumulates
from real use, not a synthetic test run.

Postman, Insomnia, and friends let you browse a schema *and* send
requests — but never connect the two. A response can silently violate
its own contract (a field goes nullable, a status narrows) and nothing
tells you. parity checks the promise against the reality, every time you
send a request.

Full design rationale, scope cuts, and data model: [`SPEC.md`](SPEC.md).

## What's real right now

Both REST (OpenAPI) and GraphQL are fully wired end to end:

- Give it a real OpenAPI URL or a real GraphQL endpoint — it fetches,
  validates, and parses the schema into a 3D graph of nodes.
- Paste a `curl` command or build a request by hand (method, URL,
  headers, body); Send fires it through a real, SSRF-guarded proxy
  against the real target API.
- The real response is matched back to the node it corresponds to and
  checked against that node's own declared schema — a real
  `jsonschema`/`graphql-core` check, not a guess. The node turns green
  (`matched`) or red (`violated`) and the finding is written to history.
- Real GitHub OAuth accounts; every workspace is scoped to the user who
  created it — one user's workspaces are genuinely invisible to another
  (enforced on every route, not just recorded).
- Encrypted-at-rest, per-workspace credentials: name a header (e.g. a
  custom `api_key` header, not just `Authorization`), set its value once,
  and it's auto-injected into every request fired against that workspace
  — never readable back out in plaintext.

## What v1 deliberately does not do

Stated plainly, not silently skipped — see `SPEC.md` §4 for the full
reasoning:

- No schema inference from traffic alone — no schema, no check.
- No mock servers, no load/performance testing, no CI-runner integration.
- No team/org sharing — workspaces are single-user.
- No OAuth2 dance on your behalf for target APIs — you paste a token you
  already have.
- HTTP(S) request/response only — no WebSockets, webhooks, or gRPC.
- GraphQL mode renders nodes with no edges yet (a real type-relationship
  layout is future frontend work); node size doesn't yet reflect real
  call frequency even though the backend already tracks it.

`HANDOFF.md` has the full, honest phase-by-phase account of what's built
and what's explicitly still open.

## Stack

- **Backend**: FastAPI, SQLAlchemy 2.x + Alembic, Postgres, `httpx` for
  the outbound proxy, `openapi-spec-validator` + `jsonschema` for REST,
  `graphql-core` for GraphQL, Fernet (`cryptography`) for credential
  encryption.
- **Frontend**: Vite + React + TypeScript, React Three Fiber / three.js
  for the 3D graph, plain CSS — a standalone visual identity, not shared
  with any other project.

## Running it locally

```bash
# 1. Postgres
cd backend && docker compose up -d
.venv/bin/... # see below for venv setup, then:
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/alembic upgrade head

# 2. Backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
GITHUB_CLIENT_ID=dev GITHUB_CLIENT_SECRET=dev \
GITHUB_CALLBACK_URL=http://localhost:8123/api/auth/github/callback \
FERNET_KEY="$(.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" \
.venv/bin/uvicorn app.main:app --port 8123

# 3. Frontend
cd frontend && npm install && npm run dev   # http://localhost:5173
```

The dev-default `GITHUB_CLIENT_ID=dev`/`GITHUB_CLIENT_SECRET=dev` above
let the app boot and every non-auth route work, but real GitHub login
needs a real registered OAuth app — see [`AUTH_SETUP.md`](AUTH_SETUP.md)
for the exact one-time steps, including the real `FERNET_KEY` a real
deploy also needs.

Run the tests:

```bash
cd backend && .venv/bin/python -m pytest -q
cd frontend && npx vitest run
```

## Deploying

[`DEPLOY.md`](DEPLOY.md) — a Render blueprint (`render.yaml`) deploys the
backend, frontend, and a managed Postgres instance in one shot; that file
covers the manual steps (registering a production OAuth app, generating
secrets) a blueprint can't do for you.

## License

MIT — see [`LICENSE`](LICENSE).
