"""Engine/session setup — sync SQLAlchemy (same reasoning as `loom`'s own
app/db.py: routes are sync `def`s FastAPI runs in its own threadpool,
nothing here is high-concurrency enough to need async SQLAlchemy)."""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://parity:parity@127.0.0.1:5441/parity"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

# Fixed, not generated — every workspace belongs to this one real row
# until Phase 3's real GitHub OAuth replaces it (SPEC.md's own Phase 1
# section). A hardcoded UUID, not looked up by name, so it never depends
# on insertion order.
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def ensure_default_user(session: Session) -> None:
    """Idempotent — safe to call on every app startup."""
    from app.models import User

    if session.get(User, DEFAULT_USER_ID) is None:
        session.add(User(id=DEFAULT_USER_ID, github_id=None, username="default"))
        session.commit()
