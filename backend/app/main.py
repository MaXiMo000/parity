import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware

from app.body_limit import MaxBodySizeMiddleware
from app.db import SessionLocal, ensure_default_user
from app.ratelimit import limiter
from app.routes.auth import router as auth_router
from app.routes.workspaces import router as workspaces_router
from app.routes.requests import router as requests_router
from app.routes.curl_parse import router as curl_parse_router

# The single controllable signal for this app's deploy posture -- default
# "development" matches today's working local-dev flow exactly (plain
# HTTP, same-origin via Vite's dev proxy, no real GitHub app required
# beyond the placeholder values AUTH_SETUP.md's dev section already
# uses). Set PARITY_ENV=production for a real deploy: it both tightens
# the session cookie's security flags (Phase 3a's final review, finding
# C1: a real split-origin deploy -- SPEC.md §12's own stated topology --
# needs SameSite=None + Secure, which would break plain-HTTP local dev if
# always on) and makes a missing required env var a boot-time failure
# instead of a confusing first-request 500 (finding I2).
PARITY_ENV = os.environ.get("PARITY_ENV", "development")
_IS_PRODUCTION = PARITY_ENV == "production"

if _IS_PRODUCTION and os.environ.get("SESSION_SECRET_KEY") is None:
    raise RuntimeError("SESSION_SECRET_KEY is required when PARITY_ENV=production (see AUTH_SETUP.md)")
for _required_var in ("GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "GITHUB_CALLBACK_URL", "FERNET_KEY"):
    if os.environ.get(_required_var) is None:
        raise RuntimeError(f"{_required_var} is required (see AUTH_SETUP.md) -- refusing to boot without it")

# A FERNET_KEY that's merely set but not a valid 32-byte urlsafe-base64
# key would otherwise boot cleanly and only fail on the first real
# encrypt/decrypt call (a confusing 500) -- construct it here too so a
# malformed key is also a boot-time failure.
if os.environ.get("FERNET_KEY") is not None:
    from cryptography.fernet import Fernet
    try:
        Fernet(os.environ["FERNET_KEY"].encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise RuntimeError(f"FERNET_KEY is not a valid Fernet key (see AUTH_SETUP.md): {exc}") from exc


@asynccontextmanager
async def lifespan(app: FastAPI):
    session = SessionLocal()
    try:
        ensure_default_user(session)
    finally:
        session.close()
    yield


app = FastAPI(title="parity", version="0.1.0", lifespan=lifespan)

# 2026-09-18 security-hardening plan: real per-route rate limits (see
# app/routes/*.py's @limiter.limit(...) decorators) and a hard cap on
# every request's declared body size, closing two real gaps a direct
# security audit found ("no rate limiting anywhere", "no request-body
# size cap on parity's own API").
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET_KEY", "dev-only-insecure-secret-change-before-any-real-deploy"),
    # A cross-site cookie (frontend and backend on different real
    # domains) needs SameSite=None, which browsers reject without
    # Secure -- the two move together. Plain HTTP local dev needs the
    # opposite (Lax + no Secure, since there's no HTTPS to require).
    same_site="none" if _IS_PRODUCTION else "lax",
    https_only=_IS_PRODUCTION,
)
app.add_middleware(
    CORSMiddleware,
    # "*" is incompatible with allow_credentials=True (the session cookie
    # needs credentialed cross-origin requests once frontend and backend
    # are on different real domains, per SPEC.md's own deploy-readiness
    # goal for this phase) -- a real, specific origin is required instead.
    allow_origins=[os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Added last -- Starlette's most-recently-added middleware runs
# outermost, so an oversized request is rejected before CORS/session
# processing even runs, not just before a route handler reads the body.
app.add_middleware(MaxBodySizeMiddleware)

app.include_router(auth_router)
app.include_router(workspaces_router)
app.include_router(requests_router)
app.include_router(curl_parse_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
