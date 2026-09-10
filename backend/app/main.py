from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.workspaces import router as workspaces_router

app = FastAPI(title="parity", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(workspaces_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
