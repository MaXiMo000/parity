"""Real disposable-Postgres discipline (this author's other project
`loom` already established this pattern for the same reason): tests run
against a real local Postgres, not sqlite or a mock."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.db import DEFAULT_USER_ID, SessionLocal, engine, ensure_default_user
from app.models import Base


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        ensure_default_user(session)
    finally:
        session.close()
    yield
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE workspace, node RESTART IDENTITY CASCADE"))
