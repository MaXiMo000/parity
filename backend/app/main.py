import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.db import SessionLocal, ensure_default_user
from app.routes.auth import router as auth_router
from app.routes.workspaces import router as workspaces_router
from app.routes.requests import router as requests_router
from app.routes.curl_parse import router as curl_parse_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    session = SessionLocal()
    try:
        ensure_default_user(session)
    finally:
        session.close()
    yield


app = FastAPI(title="parity", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET_KEY", "dev-only-insecure-secret-change-before-any-real-deploy"),
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

app.include_router(auth_router)
app.include_router(workspaces_router)
app.include_router(requests_router)
app.include_router(curl_parse_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
