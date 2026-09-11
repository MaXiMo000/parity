"""SQLAlchemy models — user/workspace/node, matching SPEC.md §7.5 exactly."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "user"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    github_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    username: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Workspace(Base):
    __tablename__ = "workspace"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("user.id"))
    name: Mapped[str] = mapped_column(String)
    schema_kind: Mapped[str] = mapped_column(String)  # "openapi" | "graphql"
    schema_source: Mapped[str] = mapped_column(Text)  # the URL, or "pasted"
    raw_schema: Mapped[dict] = mapped_column(JSONB)
    encrypted_credential: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)

    nodes: Mapped[list["Node"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")


class Node(Base):
    __tablename__ = "node"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspace.id"))
    kind: Mapped[str] = mapped_column(String)  # "rest_operation" | "graphql_field"
    method: Mapped[str | None] = mapped_column(String, nullable=True)
    path_template: Mapped[str | None] = mapped_column(String, nullable=True)
    operation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    type_name: Mapped[str | None] = mapped_column(String, nullable=True)
    field_name: Mapped[str | None] = mapped_column(String, nullable=True)
    declared_request_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    declared_response_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    call_count: Mapped[int] = mapped_column(Integer, default=0)

    workspace: Mapped[Workspace] = relationship(back_populates="nodes")
