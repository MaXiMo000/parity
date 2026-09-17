# Security Hardening — Audit + Plan

**Status:** planned, then implemented task-by-task in this same session.
Written 2026-09-18 after a direct request for a full security/UX/backend
audit ("is everything fully secured... nothing left"). The honest answer
was no — this document is the audit findings plus the plan to close the
real gaps, in priority order.

## Audit findings (verified against the actual code, not assumed)

**Real, worth-fixing gaps:**

1. **No rate limiting anywhere.** Every route, especially
   `POST /api/workspaces/{id}/requests` (fires real outbound HTTP on the
   caller's behalf) and `POST /api/workspaces` (fetches a real remote
   schema URL), is uncapped. A logged-in session — or a compromised one —
   can hammer either to abuse parity's own backend as a request-amplifier
   against a third party.
2. **No CSRF protection beyond OAuth's own `state` param.** Mutating
   routes (`POST /workspaces`, `POST .../requests`, `PUT`/`DELETE
   .../credential`, `POST /auth/logout`) rely only on the session
   cookie's `SameSite` attribute. In production (`PARITY_ENV=production`)
   the cookie is `SameSite=None` (required for the split-origin deploy),
   which removes SameSite's own CSRF protection entirely — CORS blocks a
   cross-site page's JS from *reading* the response, not from a hidden
   form *firing* the request with the ambient session cookie.
3. **No response-size cap on proxied requests.** `send_pinned`/
   `fire_request` read a target's entire response into memory (`resp.text`)
   and persist it to Postgres (`Response.body: Text`, uncapped) with no
   upper bound. A misbehaving or malicious target returning a huge body is
   a real resource-exhaustion vector.
4. **No request-body size cap on parity's own API.** Every route takes a
   raw `dict` body with no size limit — `POST .../requests`'s own `body`/
   `headers` fields are attacker-controlled and unbounded before this
   plan.
5. **No typed request validation.** Every route accepts `body: dict` and
   manually checks for the specific keys it cares about — weaker
   defense-in-depth than a real Pydantic schema rejecting anything
   malformed before a handler ever runs.
6. **A known, unaddressed dev-dependency vulnerability**: `npm audit`
   reports `@vitest/mocker` (moderate, a path-traversal/arbitrary-file-read
   advisory) — a **dev/test-only** dependency, never shipped in the built
   frontend, so real-world exposure is low, but it's sitting there
   unexamined.

**Already real and solid — re-confirmed this pass, not touched:**

- SSRF guard: DNS-pinning, redirect-hop re-validation with per-hop
  credential stripping, CGNAT/6to4/NAT64 coverage, a genuine wall-clock
  timeout (thread + `future.result(timeout=...)`, not just httpx's own
  read-timeout, which a slow-drip response can outlast).
- Real per-user ownership enforcement (404, not 403, on cross-user
  access) — adversarially tested with two real separate users.
- Fernet credential encryption at rest, with redaction of both the fixed
  sensitive-header set and any per-workspace custom credential header
  name before persisting.
- CORS locked to one explicit origin (not `*`), required alongside
  `allow_credentials=True`.
- No XSS injection points in the frontend (`grep`-confirmed: zero
  `dangerouslySetInnerHTML`/`eval`/`innerHTML` usage — React's default
  text escaping is never bypassed).

**Named, stated, and deliberately not this plan's job** (already honest
in `HANDOFF.md`, not re-litigated here): session revocation requires a
full secret rotation (no server-side session store), `same_declared_host`
is hostname-only, GraphQL matching is first-operation/first-field-only.

## Plan (executed in this order)

### Task 1: Rate limiting + body size caps

- Add `slowapi` (in-memory limiter — correct choice for this deploy
  topology: one Render web-service instance, no Redis, no need for a
  distributed limiter).
- Limits: `POST /api/workspaces` and `POST /api/workspaces/{id}/requests`
  at a conservative per-minute cap (the two routes that make parity's own
  backend fire real outbound traffic); auth routes at a looser
  brute-force-resistant cap; everything else left unlimited (read-only
  routes, and `POST /api/curl-parse` which has no side effects per its
  own docstring).
- Body size: a small ASGI middleware rejecting any request whose
  `Content-Length` exceeds a fixed cap (413) before the body is ever
  parsed — defense-in-depth for every route, not just the ones named
  above.

### Task 2: CSRF protection for mutating routes

- Double-submit-style token: a random token generated and stored in the
  session on login, returned from `GET /api/auth/me`, and required back
  as an `X-CSRF-Token` header on every mutating route. A cross-site form
  POST can't set a custom header, so this holds even under
  `SameSite=None`.
- Frontend: read the token once after login, attach it to every
  state-changing `fetch` call in `api.ts`.

### Task 3: Pydantic request models

- Replace every route's raw `body: dict` with a real `BaseModel` --
  `create_workspace`, `send_request`, `set_credential`, `curl_parse`.
  Verified safe against the existing test suite: no test asserts exact
  422 error body content, only status codes, and FastAPI's own
  `RequestValidationError` already maps to 422 — this is a behavior-
  preserving refactor, not a breaking one.

### Task 4 (if time allows): dev-dependency vulnerability

- `npm audit fix` (not `--force`, which would jump `vitest` to a new
  major version) — check first whether a non-breaking fix exists; if not,
  evaluate the `--force` breaking upgrade path separately rather than
  taking it blindly.

## Explicitly out of scope for this plan

- Distributed/Redis-backed rate limiting — this deploy is one instance;
  revisit only if the topology changes.
- A full secrets-manager migration for `FERNET_KEY`/`SESSION_SECRET_KEY`
  — already honestly scoped in SPEC.md §7.4 as "defends against a
  database dump, not a full secrets-manager setup."
- Security response headers (CSP/HSTS/X-Frame-Options) on the static
  frontend — a Render static-site config concern, not application code;
  worth a follow-up but not bundled into this backend-focused plan.
