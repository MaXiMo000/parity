from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import SessionLocal, ensure_default_user
from app.routes.workspaces import router as workspaces_router
from app.routes.requests import router as requests_router


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
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(workspaces_router)
app.include_router(requests_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
