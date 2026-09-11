# Phase 1a: Postgres + Real OpenAPI Parsing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Phase 0's hand-written fixture with real persistence and
real schema ingestion: a user gives a real OpenAPI URL, the backend fetches
and parses it for real, persists workspace+nodes to a real Postgres, and
the frontend renders the real resulting graph — no more `phase0-fixture-workspace`.

**Architecture:** SQLAlchemy models (`User`, `Workspace`, `Node`) + Alembic
migrations against a real Postgres (matching this author's other project
`loom`'s exact pattern — same stack, no code shared). A pure `openapi.py`
module fetches+validates+parses a real OpenAPI 3.x spec into flat node
data, resolving every `$ref` pointer inline (real specs are full of them —
confirmed against a real fetched spec, not assumed) so each node's
declared schema is immediately usable without a caller needing the whole
document. A pure `edges.py` module groups nodes into a REST hierarchy by
shared resource prefix. Real routes replace the Phase 0 fixture routes;
the fake `POST .../requests` from Phase 0 is replaced with an honest
"not yet implemented" response (Phase 2's real job) rather than removed
outright — the route shape stays real, only its behavior changes.

**Split note (writing-plans skill's own decomposition guidance):** SPEC.md's
Phase 1 covers both OpenAPI and GraphQL ingestion — genuinely independent
subsystems (different libraries, different graph shapes, sharing only the
`node` table). This plan covers OpenAPI only. GraphQL introspection/SDL
parsing is a separate follow-up plan ("Phase 1b"), sequenced after this one
lands and is live-verified, not bundled in.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Alembic, Postgres (psycopg),
httpx, PyYAML, pytest; existing frontend stack unchanged (Vite/React/R3F).

**Spec:** `SPEC.md` (repo root) — this plan implements the OpenAPI half of
§10 Phase 1. `HANDOFF.md` records the Phase 0 → Phase 1a decisions this
plan makes.

## Global Constraints

- Node field names must match SPEC.md §7.5's real `node` columns exactly:
  `id, workspace_id, kind, method, path_template, operation_id, type_name,
  field_name, declared_request_schema, declared_response_schema,
  call_count`. `type_name`/`field_name` stay `NULL` for every REST node
  (GraphQL-only, Phase 1b).
- Workspace field names match §7.5's `workspace` columns:
  `id, user_id, name, schema_kind, schema_source, raw_schema,
  encrypted_credential, created_at, updated_at`. `encrypted_credential`
  stays `NULL` (Phase 3, real accounts/credentials).
- **No OAuth yet.** Every workspace belongs to one real, fixed default
  `User` row this plan's Task 1 creates at app startup (idempotent — safe
  to run against an already-migrated DB) — not a nullable `user_id`, a
  real row, per SPEC.md's own Phase 1 section: "a real migration
  reassigning ownership" is how Phase 3's real accounts replace this,
  not a schema change from nullable to non-nullable after the fact.
- **`$ref` pointers must be resolved inline before a node's
  `declared_request_schema`/`declared_response_schema` is stored** — a
  real fetched OpenAPI spec (this plan's own test fixture,
  `tests/fixtures/petstore-openapi.json`) uses `$ref` for essentially
  every schema; storing the raw pointer would make the field useless to
  any consumer that doesn't also have the whole document. Local pointers
  only (`#/components/...`) — no external file/URL refs (SPEC.md's own
  no-live-resolution discipline extends here: this parses what's declared
  in the one document given, nothing it points outside of).
- A node's `declared_response_schema` is its **first 2xx response's**
  `application/json` schema only — not the full per-status-code response
  map (SPEC.md §7.5 has one schema field per node, not one per status).
  State this simplification in code comments, don't silently narrow it.
- Git identity: `git config user.email` in this repo must already be
  `109451965+MaXiMo000@users.noreply.github.com`, `user.name` must be
  `MaXiMo000` (both already set correctly as of Phase 0 — confirm, don't
  re-set blindly).
- Direct commits to `main`, no feature branch (same as Phase 0, same
  standing consent).

---

### Task 1: SQLAlchemy models, Alembic, Postgres

**Files:**
- Create: `backend/app/models.py`
- Create: `backend/app/db.py`
- Create: `backend/docker-compose.yml`
- Modify: `backend/pyproject.toml` (add `sqlalchemy`, `alembic`, `psycopg[binary]`, `httpx`, `PyYAML`)
- Create: `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`, `backend/alembic/versions/` (via `alembic init`/`alembic revision --autogenerate`, not hand-written)
- Modify: `backend/app/main.py` (startup event creating the default user)
- Create: `backend/tests/conftest.py`

**Interfaces:**
- Produces: `app.models.Base`, `app.models.User(id, github_id, username, created_at)`,
  `app.models.Workspace(id, user_id, name, schema_kind, schema_source,
  raw_schema, encrypted_credential, created_at, updated_at)`,
  `app.models.Node(id, workspace_id, kind, method, path_template,
  operation_id, type_name, field_name, declared_request_schema,
  declared_response_schema, call_count)`.
- Produces: `app.db.engine`, `app.db.SessionLocal`, `app.db.get_session()` (FastAPI dependency generator).
- Produces: `app.db.DEFAULT_USER_ID: str` (a fixed constant, e.g. a hardcoded UUID string) and `app.db.ensure_default_user(session) -> None` (idempotent upsert).

- [ ] **Step 1: Add dependencies to `backend/pyproject.toml`**

Add to the `dependencies` list: `"sqlalchemy>=2.0"`, `"alembic>=1.13"`,
`"psycopg[binary]>=3.1"`, `"httpx>=0.27"`, `"PyYAML>=6.0"`. Add
`"respx>=0.21"` to the `dev` extras (for mocking httpx in later tasks'
tests).

- [ ] **Step 2: Write `backend/app/models.py`**

```python
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
```

- [ ] **Step 3: Write `backend/app/db.py`**

```python
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
```

- [ ] **Step 4: Write `backend/docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: parity
      POSTGRES_PASSWORD: parity
      POSTGRES_DB: parity
    ports:
      # 127.0.0.1 is load-bearing, not decoration (same lesson recur's own
      # docker-compose.yml and loom's copy of it already learned) — plain
      # "5441:5432" binds 0.0.0.0. 5441 avoids colliding with a locally
      # installed Postgres or loom's own dev instance on 5439.
      - "127.0.0.1:5441:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U parity"]
      interval: 3s
      retries: 10

volumes:
  pgdata:
```

- [ ] **Step 5: Start Postgres and install dependencies**

Run: `cd backend && docker compose up -d`
Run: `.venv/bin/pip install -e ".[dev]"` (the venv already exists from Phase 0)

- [ ] **Step 6: Initialize Alembic and generate the first migration**

Run: `cd backend && .venv/bin/alembic init -t generic alembic`

Edit the generated `backend/alembic/env.py`: add near the top, after the
existing imports —

```python
from app.db import DATABASE_URL
from app.models import Base
```

— then replace the line `target_metadata = None` with
`target_metadata = Base.metadata`, and right after the `config = context.config`
line, add:

```python
config.set_main_option("sqlalchemy.url", DATABASE_URL)
```

Run: `DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/alembic revision --autogenerate -m "initial user/workspace/node tables"`
Run: `DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/alembic upgrade head`

Verify the migration applied: `docker compose exec db psql -U parity -d parity -c '\dt'` should list `user`, `workspace`, `node`, `alembic_version`.

- [ ] **Step 7: Wire `ensure_default_user` into app startup — modify `backend/app/main.py`**

Add a startup event. Read the current `backend/app/main.py` first (it's
Phase 0's version with the fixture routes still wired in — leave those
routes alone for now, Task 3 replaces them). Add:

```python
from app.db import SessionLocal, ensure_default_user

@app.on_event("startup")
def on_startup() -> None:
    session = SessionLocal()
    try:
        ensure_default_user(session)
    finally:
        session.close()
```

- [ ] **Step 8: Write `backend/tests/conftest.py`**

```python
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
```

- [ ] **Step 9: Verify the app still starts with the new startup event**

Run: `cd backend && DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/uvicorn app.main:app --port 8123 &`
then `sleep 1 && curl -s http://127.0.0.1:8123/health && kill %1`
Expected: `{"status":"ok"}`, and check the startup log shows no errors.
Then verify the default user row exists: `docker compose exec db psql -U parity -d parity -c 'select id, username from "user";'` should show exactly one row with username `default`.

- [ ] **Step 10: Commit**

```bash
cd backend && git add pyproject.toml app/models.py app/db.py app/main.py \
  docker-compose.yml alembic.ini alembic/ tests/conftest.py
git commit -m "backend: SQLAlchemy models, Alembic, Postgres, default user"
```

---

### Task 2: Real OpenAPI parsing (fetch, validate, resolve `$ref`, flatten to nodes) + REST edge grouping

**Files:**
- Create: `backend/app/schema/__init__.py`
- Create: `backend/app/schema/openapi.py`
- Create: `backend/app/edges.py`
- Create: `backend/tests/fixtures/petstore-openapi.json` (already fetched — copy from `/Users/ritis/Documents/Personal/parity/backend/tests/fixtures/petstore-openapi.json` if it already exists at that path from prior setup; if not, fetch fresh: `curl -s https://petstore3.swagger.io/api/v3/openapi.json -o backend/tests/fixtures/petstore-openapi.json`)
- Create: `backend/tests/test_openapi_schema.py`
- Create: `backend/tests/test_edges.py`

**Interfaces:**
- Produces: `app.schema.openapi.fetch_spec(source: str) -> dict` (source is
  a URL; raises `OpenAPIFetchError` on network failure or invalid
  JSON/YAML), `app.schema.openapi.parse_openapi(spec: dict) -> list[dict]`
  (each dict has keys: `kind, method, path_template, operation_id,
  declared_request_schema, declared_response_schema` — no `id` yet, the
  caller/DB assigns that), `app.schema.openapi.OpenAPIValidationError`
  (raised by `parse_openapi` if the spec fails `openapi-spec-validator`).
- Produces: `app.edges.compute_rest_edges(nodes: list[dict]) -> list[tuple[str, str]]`
  — takes node dicts that already have a real `id` (post-DB-insert shape),
  returns `(from_node_id, to_node_id)` pairs.

- [ ] **Step 1: Confirm the real fixture is in place**

Run: `ls -la backend/tests/fixtures/petstore-openapi.json` — if missing,
fetch it: `curl -s https://petstore3.swagger.io/api/v3/openapi.json -o backend/tests/fixtures/petstore-openapi.json`.
This is a real, live, publicly-served OpenAPI spec (the standard Swagger
Petstore example) — 13 paths, real `$ref`-based schemas, used here as a
committed fixture per SPEC.md §11's "real fixtures, not synthetic
one-liners" discipline.

- [ ] **Step 2: Write the failing tests `backend/tests/test_openapi_schema.py`**

```python
import json
from pathlib import Path

import httpx
import pytest
import respx

from app.schema.openapi import (
    OpenAPIValidationError,
    fetch_spec,
    parse_openapi,
)

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "petstore-openapi.json").read_text())


def test_parse_real_petstore_spec_produces_real_nodes():
    nodes = parse_openapi(FIXTURE)
    assert len(nodes) > 10  # the real spec has 13 paths, several with >1 method

    by_op = {n["operation_id"]: n for n in nodes}
    assert "addPet" in by_op
    add_pet = by_op["addPet"]
    assert add_pet["method"] == "POST"
    assert add_pet["path_template"] == "/pet"
    assert add_pet["kind"] == "rest_operation"


def test_dollar_refs_are_resolved_inline_not_left_as_pointers():
    nodes = parse_openapi(FIXTURE)
    by_op = {n["operation_id"]: n for n in nodes}
    add_pet = by_op["addPet"]
    # The real spec's addPet.requestBody is `{"$ref": "#/components/schemas/Pet"}` —
    # after resolution this must be the real Pet schema, not the pointer.
    assert "$ref" not in json.dumps(add_pet["declared_request_schema"])
    assert add_pet["declared_request_schema"]["type"] == "object"
    assert "name" in add_pet["declared_request_schema"]["properties"]


def test_response_schema_is_the_first_2xx_only():
    nodes = parse_openapi(FIXTURE)
    by_op = {n["operation_id"]: n for n in nodes}
    add_pet = by_op["addPet"]
    # addPet's real responses are 200/400/422/default -- only 200's schema
    # should be stored (this plan's own stated simplification).
    assert add_pet["declared_response_schema"] is not None
    assert "$ref" not in json.dumps(add_pet["declared_response_schema"])


def test_operation_with_no_request_body_has_null_request_schema():
    nodes = parse_openapi(FIXTURE)
    by_op = {n["operation_id"]: n for n in nodes}
    # findPetsByStatus is a real GET with no body.
    assert by_op["findPetsByStatus"]["declared_request_schema"] is None


def test_invalid_spec_raises_validation_error():
    with pytest.raises(OpenAPIValidationError):
        parse_openapi({"not": "a real openapi spec"})


@respx.mock
def test_fetch_spec_real_http_get():
    respx.get("https://example.invalid/openapi.json").mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    spec = fetch_spec("https://example.invalid/openapi.json")
    assert spec["info"]["title"] == FIXTURE["info"]["title"]


@respx.mock
def test_fetch_spec_network_failure_raises():
    from app.schema.openapi import OpenAPIFetchError

    respx.get("https://example.invalid/openapi.json").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(OpenAPIFetchError):
        fetch_spec("https://example.invalid/openapi.json")
```

- [ ] **Step 3: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_openapi_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.schema'`

- [ ] **Step 4: Write `backend/app/schema/__init__.py`** (empty)

- [ ] **Step 5: Write `backend/app/schema/openapi.py`**

```python
"""Real OpenAPI 3.x ingestion: fetch a real spec, validate it, flatten
its operations into node data with every `$ref` resolved inline.

Real fetched specs (tests/fixtures/petstore-openapi.json, the standard
Swagger Petstore example) use `$ref` for essentially every schema — a
node's declared_request_schema/declared_response_schema would be useless
to any consumer without also holding the whole document, so this resolves
every local `#/...` pointer before a node is ever built. Local pointers
only: no external file/URL refs (SPEC.md's own no-live-resolution
discipline extends here)."""

from __future__ import annotations

from typing import Any

import httpx
from openapi_spec_validator import validate

_HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


class OpenAPIFetchError(Exception):
    pass


class OpenAPIValidationError(Exception):
    pass


def fetch_spec(source: str) -> dict[str, Any]:
    """`source` is a URL. Raises OpenAPIFetchError on any network failure
    or unparseable body (JSON or YAML, real specs are published as either)."""
    try:
        resp = httpx.get(source, timeout=15.0, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise OpenAPIFetchError(f"could not reach {source}: {exc}") from exc
    if resp.status_code != 200:
        raise OpenAPIFetchError(f"{source} returned HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError:
        pass
    try:
        import yaml

        return yaml.safe_load(resp.text)
    except Exception as exc:  # noqa: BLE001 -- any YAML parse failure is a fetch-shaped failure here
        raise OpenAPIFetchError(f"{source} is neither valid JSON nor YAML") from exc


def _resolve_refs(node: Any, root: dict[str, Any], seen: frozenset[str] = frozenset()) -> Any:
    """Recursively replaces every local `$ref` pointer with the fragment
    it points to. `seen` guards against a genuinely recursive schema
    (e.g. a tree-shaped type referencing itself) turning into infinite
    recursion -- a ref already being resolved higher up the same branch
    is left as a pointer rather than expanded again."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/"):
            if ref in seen:
                return {"$ref": ref}  # break the cycle, leave the pointer
            target: Any = root
            for part in ref[2:].split("/"):
                target = target[part]
            return _resolve_refs(target, root, seen | {ref})
        return {k: _resolve_refs(v, root, seen) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve_refs(v, root, seen) for v in node]
    return node


def _first_2xx_response_schema(responses: dict[str, Any], spec: dict[str, Any]) -> dict | None:
    for status in sorted(responses):
        if status.startswith("2"):
            schema = responses[status].get("content", {}).get("application/json", {}).get("schema")
            return _resolve_refs(schema, spec) if schema is not None else None
    return None


def parse_openapi(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Returns a flat list of node dicts (no `id` -- the caller/DB assigns
    that), one per (path, method) operation. Raises OpenAPIValidationError
    if the spec doesn't validate as real OpenAPI 3.x."""
    try:
        validate(spec)
    except Exception as exc:  # noqa: BLE001 -- verified against the real library (2026-09-11): a
        # missing/unrecognized version key raises ValidatorDetectError, a
        # present-but-malformed spec raises OpenAPIValidationError -- the
        # two share no common base except Exception itself (confirmed via
        # their real __mro__), so this catches both deliberately rather
        # than guessing at one specific class or import path.
        raise OpenAPIValidationError(f"not a valid OpenAPI document: {exc}") from exc

    nodes: list[dict[str, Any]] = []
    for path, path_item in spec.get("paths", {}).items():
        for method in _HTTP_METHODS:
            op = path_item.get(method)
            if op is None:
                continue
            operation_id = op.get("operationId") or f"{method}_{path}".replace("/", "_").replace("{", "").replace("}", "")
            request_schema = None
            body = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
            if body is not None:
                request_schema = _resolve_refs(body, spec)
            response_schema = _first_2xx_response_schema(op.get("responses", {}), spec)

            nodes.append({
                "kind": "rest_operation",
                "method": method.upper(),
                "path_template": path,
                "operation_id": operation_id,
                "type_name": None,
                "field_name": None,
                "declared_request_schema": request_schema,
                "declared_response_schema": response_schema,
            })
    return nodes
```

- [ ] **Step 6: Run to verify the openapi tests pass**

Run: `.venv/bin/python -m pytest tests/test_openapi_schema.py -v`
Expected: PASS (6 passed)

- [ ] **Step 7: Write the failing tests `backend/tests/test_edges.py`**

```python
from app.edges import compute_rest_edges


def _node(id_, path):
    return {"id": id_, "path_template": path}


def test_nodes_sharing_a_resource_prefix_are_chained():
    nodes = [
        _node("a", "/pets"),
        _node("b", "/pets/{id}"),
        _node("c", "/pets/{id}/photos"),
    ]
    edges = compute_rest_edges(nodes)
    ids_in_edges = {i for pair in edges for i in pair}
    assert ids_in_edges == {"a", "b", "c"}
    assert len(edges) == 2  # a chain of 3 nodes has 2 edges


def test_nodes_in_different_resources_are_not_connected():
    nodes = [_node("a", "/pets"), _node("b", "/orders")]
    assert compute_rest_edges(nodes) == []


def test_real_petstore_shape_produces_a_real_multi_group_graph():
    # Mirrors the real fixture's actual top-level resources: pet, store, user.
    nodes = [
        _node("1", "/pet"), _node("2", "/pet/{petId}"), _node("3", "/pet/findByStatus"),
        _node("4", "/store/order"), _node("5", "/store/inventory"),
        _node("6", "/user"),
    ]
    edges = compute_rest_edges(nodes)
    connected = {i for pair in edges for i in pair}
    assert "6" not in connected  # /user is alone in its group -> no edges for it
    assert {"1", "2", "3"} & connected == {"1", "2", "3"}
    assert {"4", "5"} & connected == {"4", "5"}
```

- [ ] **Step 8: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_edges.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.edges'`

- [ ] **Step 9: Write `backend/app/edges.py`**

```python
"""REST edges for the 3D graph (SPEC.md §8.3's "tree/force-graph by path
and tag"): purely derived from path_template, never persisted -- nothing
here needs its own migration or table, it's recomputed whenever a
workspace's graph is served."""

from __future__ import annotations

from collections import defaultdict


def _resource_key(path_template: str) -> str:
    parts = [p for p in path_template.split("/") if p]
    return parts[0] if parts else "/"


def compute_rest_edges(nodes: list[dict]) -> list[tuple[str, str]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for n in nodes:
        groups[_resource_key(n["path_template"])].append(n)

    edges: list[tuple[str, str]] = []
    for group_nodes in groups.values():
        ordered = sorted(group_nodes, key=lambda n: len(n["path_template"]))
        for a, b in zip(ordered, ordered[1:]):
            edges.append((a["id"], b["id"]))
    return edges
```

- [ ] **Step 10: Run to verify both test files pass**

Run: `.venv/bin/python -m pytest tests/test_openapi_schema.py tests/test_edges.py -v`
Expected: PASS (9 passed total)

- [ ] **Step 11: Commit**

```bash
git add app/schema/ app/edges.py tests/fixtures/petstore-openapi.json \
  tests/test_openapi_schema.py tests/test_edges.py
git commit -m "backend: real OpenAPI parsing with \$ref resolution + REST edge grouping"
```

---

### Task 3: Real workspace routes (create/list/get), replacing the Phase 0 fixture

**Files:**
- Modify: `backend/app/routes/workspaces.py` (full rewrite)
- Modify: `backend/app/main.py` (remove fixture-router import if separate — check current content first)
- Delete: `backend/app/fixtures.py`
- Modify: `backend/tests/test_workspace_routes.py` (full rewrite for real DB + real parsing)

**Interfaces:**
- Consumes: `app.schema.openapi.fetch_spec`, `parse_openapi`,
  `OpenAPIFetchError`, `OpenAPIValidationError` (Task 2);
  `app.edges.compute_rest_edges` (Task 2); `app.models.User, Workspace,
  Node` (Task 1); `app.db.get_session, DEFAULT_USER_ID` (Task 1).
- Produces: `POST /api/workspaces` accepting `{"name": str, "schema_kind":
  "openapi", "schema_source_url": str}` OR `{"name": str, "schema_kind":
  "openapi", "raw_schema": dict}` (exactly one of `schema_source_url`/
  `raw_schema` required) → `{"id": str, "name": str, "schema_kind": str,
  "node_count": int}` on success, `422` if the spec doesn't validate or
  neither/both source fields are given, `502` if the URL fetch fails.
  `GET /api/workspaces` → `[{"id", "name", "schema_kind"}, ...]` (real DB
  rows, scoped to `DEFAULT_USER_ID`). `GET /api/workspaces/{id}` →
  `{"id", "name", "schema_kind", "nodes": [...], "edges": [{"from_node",
  "to_node"}, ...]}` — same response shape Phase 0's frontend already
  expects, now real.

- [ ] **Step 1: Read the current `backend/app/routes/workspaces.py` and `backend/app/main.py`**

Understand exactly what Phase 0 left in place before rewriting — Phase 0's
version imports from `app.fixtures`, which this task deletes.

- [ ] **Step 2: Write the failing tests — full rewrite of `backend/tests/test_workspace_routes.py`**

```python
import json
from pathlib import Path

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "petstore-openapi.json").read_text())


@respx.mock
def test_create_workspace_from_a_real_url():
    respx.get("https://example.invalid/openapi.json").mock(return_value=httpx.Response(200, json=FIXTURE))
    r = client.post("/api/workspaces", json={
        "name": "Petstore", "schema_kind": "openapi",
        "schema_source_url": "https://example.invalid/openapi.json",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Petstore"
    assert body["node_count"] > 10


def test_create_workspace_from_a_pasted_raw_schema():
    r = client.post("/api/workspaces", json={
        "name": "Petstore (pasted)", "schema_kind": "openapi", "raw_schema": FIXTURE,
    })
    assert r.status_code == 200
    assert r.json()["node_count"] > 10


def test_create_workspace_requires_exactly_one_source():
    r = client.post("/api/workspaces", json={"name": "x", "schema_kind": "openapi"})
    assert r.status_code == 422
    r2 = client.post("/api/workspaces", json={
        "name": "x", "schema_kind": "openapi",
        "schema_source_url": "https://example.invalid/x.json", "raw_schema": FIXTURE,
    })
    assert r2.status_code == 422


def test_create_workspace_rejects_an_invalid_spec():
    r = client.post("/api/workspaces", json={
        "name": "bad", "schema_kind": "openapi", "raw_schema": {"not": "openapi"},
    })
    assert r.status_code == 422


@respx.mock
def test_create_workspace_url_fetch_failure_is_502():
    respx.get("https://example.invalid/down.json").mock(side_effect=httpx.ConnectError("boom"))
    r = client.post("/api/workspaces", json={
        "name": "x", "schema_kind": "openapi", "schema_source_url": "https://example.invalid/down.json",
    })
    assert r.status_code == 502


def test_list_and_get_real_workspace():
    created = client.post("/api/workspaces", json={
        "name": "Petstore", "schema_kind": "openapi", "raw_schema": FIXTURE,
    }).json()

    listed = client.get("/api/workspaces").json()
    assert any(w["id"] == created["id"] for w in listed)

    got = client.get(f"/api/workspaces/{created['id']}").json()
    assert got["name"] == "Petstore"
    assert len(got["nodes"]) == created["node_count"]
    assert len(got["edges"]) > 0
    node_ids = {n["id"] for n in got["nodes"]}
    for e in got["edges"]:
        assert e["from_node"] in node_ids
        assert e["to_node"] in node_ids
    # real field names, matching SPEC.md §7.5
    sample = got["nodes"][0]
    for key in ("id", "kind", "method", "path_template", "operation_id",
                "declared_request_schema", "declared_response_schema", "call_count"):
        assert key in sample


def test_get_unknown_workspace_is_404():
    r = client.get("/api/workspaces/00000000-0000-0000-0000-000000000099")
    assert r.status_code == 404
```

- [ ] **Step 3: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_workspace_routes.py -v`
Expected: FAIL (old fixture-based tests/routes still in place)

- [ ] **Step 4: Rewrite `backend/app/routes/workspaces.py`**

```python
"""POST/GET /api/workspaces — real Phase 1 behavior: fetches or accepts a
real OpenAPI spec, parses it for real (app/schema/openapi.py), persists
workspace+nodes to real Postgres. Replaces Phase 0's fixture routes
entirely."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import DEFAULT_USER_ID, get_session
from app.edges import compute_rest_edges
from app.models import Node, Workspace
from app.schema.openapi import OpenAPIFetchError, OpenAPIValidationError, fetch_spec, parse_openapi

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.post("")
def create_workspace(body: dict, session: Session = Depends(get_session)) -> dict:
    name = body.get("name")
    schema_kind = body.get("schema_kind")
    url = body.get("schema_source_url")
    raw = body.get("raw_schema")
    if not name or schema_kind != "openapi":
        raise HTTPException(status_code=422, detail="name and schema_kind='openapi' are required")
    if bool(url) == bool(raw):
        raise HTTPException(status_code=422, detail="exactly one of schema_source_url or raw_schema is required")

    if url:
        try:
            spec = fetch_spec(url)
        except OpenAPIFetchError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    else:
        spec = raw

    try:
        parsed_nodes = parse_openapi(spec)
    except OpenAPIValidationError as exc:
        raise HTTPException(status_code=422, detail=f"invalid OpenAPI spec: {exc}") from exc

    workspace = Workspace(
        user_id=DEFAULT_USER_ID, name=name, schema_kind="openapi",
        schema_source=url or "pasted", raw_schema=spec,
    )
    session.add(workspace)
    session.flush()

    for pn in parsed_nodes:
        session.add(Node(workspace_id=workspace.id, **pn))
    session.commit()

    return {"id": workspace.id, "name": workspace.name, "schema_kind": workspace.schema_kind,
            "node_count": len(parsed_nodes)}


@router.get("")
def list_workspaces(session: Session = Depends(get_session)) -> list[dict]:
    rows = session.query(Workspace).filter(Workspace.user_id == DEFAULT_USER_ID).all()
    return [{"id": w.id, "name": w.name, "schema_kind": w.schema_kind} for w in rows]


@router.get("/{workspace_id}")
def get_workspace(workspace_id: str, session: Session = Depends(get_session)) -> dict:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="unknown workspace id")

    node_dicts = [
        {
            "id": n.id, "kind": n.kind, "method": n.method, "path_template": n.path_template,
            "operation_id": n.operation_id, "type_name": n.type_name, "field_name": n.field_name,
            "declared_request_schema": n.declared_request_schema,
            "declared_response_schema": n.declared_response_schema, "call_count": n.call_count,
        }
        for n in workspace.nodes
    ]
    edges = compute_rest_edges([{"id": n["id"], "path_template": n["path_template"]} for n in node_dicts])

    return {
        "id": workspace.id, "name": workspace.name, "schema_kind": workspace.schema_kind,
        "nodes": node_dicts,
        "edges": [{"from_node": a, "to_node": b} for a, b in edges],
    }
```

- [ ] **Step 5: Delete `backend/app/fixtures.py`**

Run: `git rm backend/app/fixtures.py`

- [ ] **Step 6: Update `backend/app/main.py`** to remove any remaining
  reference to the old fixture-based behavior (the router import/include
  for `workspaces_router` stays — only its internal implementation
  changed in Step 4). Read the file first; only touch what's actually
  stale.

- [ ] **Step 7: Run the full backend test suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass (Task 1/2's tests plus this task's — old
fixture-based tests for `workspaces.py` no longer exist since this task
replaced that file entirely).

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "backend: real workspace routes (create/list/get) backed by Postgres + real OpenAPI parsing"
```

---

### Task 4: Honest "not yet implemented" send route

**Files:**
- Modify: `backend/app/routes/requests.py` (full rewrite)
- Modify: `backend/tests/test_request_routes.py` (full rewrite)

**Interfaces:**
- Produces: `POST /api/workspaces/{workspace_id}/requests` → `501` with
  `{"detail": "real request execution arrives in Phase 2"}` for any real,
  existing workspace; `404` for an unknown workspace id. Same route path
  as Phase 0 (so the frontend's `sendRequest()` call in `api.ts` doesn't
  need a URL change), honest behavior instead of Phase 0's canned fake
  result.

- [ ] **Step 1: Write the failing tests — full rewrite of `backend/tests/test_request_routes.py`**

```python
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_send_against_a_real_workspace_is_honestly_not_implemented():
    ws = client.post("/api/workspaces", json={
        "name": "x", "schema_kind": "openapi",
        "raw_schema": {"openapi": "3.0.0", "info": {"title": "t", "version": "1"}, "paths": {}},
    }).json()
    r = client.post(f"/api/workspaces/{ws['id']}/requests", json={"node_id": "whatever"})
    assert r.status_code == 501
    assert "Phase 2" in r.json()["detail"]


def test_send_against_unknown_workspace_is_404():
    r = client.post("/api/workspaces/00000000-0000-0000-0000-000000000099/requests", json={"node_id": "x"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_request_routes.py -v`
Expected: FAIL (old fake-canned-response behavior still in place)

- [ ] **Step 3: Rewrite `backend/app/routes/requests.py`**

```python
"""POST /api/workspaces/{id}/requests — Phase 0 returned a canned fake
result per fixture node; Phase 1 has real workspaces but no real request
proxying yet (that's Phase 2's SSRF-guarded proxy, SPEC.md §7.3). Rather
than removing this route (the frontend's Send button already calls it,
and the route SHAPE is real v1 API surface per SPEC.md §7.6), it now
answers honestly: 501, not a guess."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Workspace

router = APIRouter(prefix="/api/workspaces", tags=["requests"])


@router.post("/{workspace_id}/requests")
def send_request(workspace_id: str, body: dict, session: Session = Depends(get_session)) -> dict:
    if session.get(Workspace, workspace_id) is None:
        raise HTTPException(status_code=404, detail="unknown workspace id")
    raise HTTPException(status_code=501, detail="real request execution arrives in Phase 2 (SPEC.md §7.3/§10)")
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/routes/requests.py tests/test_request_routes.py
git commit -m "backend: honest 501 for request-sending until Phase 2, not a fake result"
```

---

### Task 5: Frontend — real create-workspace flow

**Files:**
- Modify: `frontend/src/api.ts`
- Create: `frontend/src/components/WorkspaceForm.tsx`
- Modify: `frontend/src/App.tsx` (full rewrite)
- Modify: `frontend/src/components/DetailPanel.tsx` (handle the 501 gracefully)
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Produces (`api.ts`): `createWorkspace(name: string, source: {url: string} | {rawSchema: object}): Promise<{id: string; name: string; schema_kind: string; node_count: number}>`,
  `listWorkspaces(): Promise<WorkspaceSummary[]>` (already existed, unused since Phase 0 — now used for real), `getWorkspace` unchanged in shape.
  `Node` interface gains `type_name: string | null` and `field_name: string | null` (real Phase 1 fields, always null for REST — matches the backend's real response shape now).
- `App.tsx` no longer imports or references `FIXTURE_ID` at all.

- [ ] **Step 1: Update `frontend/src/api.ts`**

Read the current file first. Add the two new nullable fields to `Node`,
and add `createWorkspace`:

```ts
export interface Node {
  id: string
  kind: 'rest_operation'
  method: string | null
  path_template: string | null
  operation_id: string | null
  type_name: string | null
  field_name: string | null
  declared_request_schema: Record<string, unknown> | null
  declared_response_schema: Record<string, unknown> | null
  call_count: number
}
```

Add:

```ts
export function createWorkspace(
  name: string,
  source: { url: string } | { rawSchema: object },
): Promise<{ id: string; name: string; schema_kind: string; node_count: number }> {
  const body =
    'url' in source
      ? { name, schema_kind: 'openapi', schema_source_url: source.url }
      : { name, schema_kind: 'openapi', raw_schema: source.rawSchema }
  return fetch('/api/workspaces', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then((res) => json<{ id: string; name: string; schema_kind: string; node_count: number }>(res))
}
```

(`listWorkspaces`/`getWorkspace`/`sendRequest`/`WorkspaceSummary`/`Workspace`/`Edge` all already exist from Phase 0 — leave them as-is unless the `Node` change above requires an adjacent type fix.)

- [ ] **Step 2: Write `frontend/src/components/WorkspaceForm.tsx`**

```tsx
import { useState } from 'react'

/** The real "give it a schema" entry point (SPEC.md §6 step 1) — a real
 * OpenAPI URL, submitted for real parsing. Pasting a raw spec is the v1
 * stand-in for real file upload (SPEC.md §3's own "either is fine, don't
 * block on this" spirit, applied here to upload vs. paste). */
export function WorkspaceForm({ onCreate, busy }: {
  onCreate: (name: string, url: string) => void
  busy: boolean
}) {
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')

  return (
    <form
      className="workspace-form"
      onSubmit={(e) => {
        e.preventDefault()
        if (name.trim() && url.trim()) onCreate(name.trim(), url.trim())
      }}
    >
      <input
        type="text" placeholder="Workspace name" value={name}
        onChange={(e) => setName(e.target.value)} disabled={busy} aria-label="Workspace name"
      />
      <input
        type="text" placeholder="https://api.example.com/openapi.json" value={url}
        onChange={(e) => setUrl(e.target.value)} disabled={busy} aria-label="OpenAPI URL"
      />
      <button type="submit" disabled={busy || !name.trim() || !url.trim()}>
        {busy ? 'Parsing…' : 'Create'}
      </button>
    </form>
  )
}
```

- [ ] **Step 3: Rewrite `frontend/src/App.tsx`**

Read the current file first (Phase 0's version with `FIXTURE_ID`,
`statuses`, `history`, `diff` state — this rewrite removes the hardcoded
fixture load and replaces it with the real create-workspace flow; keep
the detail-panel/Send/statuses machinery, it's still real and correct):

```tsx
import { useCallback, useEffect, useState } from 'react'
import { createWorkspace, getWorkspace, sendRequest, type Workspace } from './api'
import { DetailPanel } from './components/DetailPanel'
import { WorkspaceForm } from './components/WorkspaceForm'
import type { DriftStatus } from './lib/severity'
import { Graph } from './scene/Graph'

export function App() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [statuses, setStatuses] = useState<Record<string, DriftStatus>>({})
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleClose = useCallback(() => setSelectedId(null), [])

  function handleCreate(name: string, url: string) {
    setBusy(true)
    setError(null)
    createWorkspace(name, { url })
      .then((created) => getWorkspace(created.id))
      .then((ws) => { setWorkspace(ws); setStatuses({}) })
      .catch((e) => setError(String(e)))
      .finally(() => setBusy(false))
  }

  async function handleSend(nodeId: string) {
    if (!workspace) throw new Error('no workspace loaded')
    const result = await sendRequest(workspace.id, nodeId)
    setStatuses((prev) => ({ ...prev, [nodeId]: result.drift_finding.status }))
    return result
  }

  const selected = workspace?.nodes.find((n) => n.id === selectedId) ?? null

  return (
    <div className="app">
      <div className="scene-root">
        <div className="hud-top">
          <div className="brand">parity<span>.</span></div>
          <WorkspaceForm onCreate={handleCreate} busy={busy} />
        </div>

        {!workspace && !error && (
          <p className="idle-hint">Paste a real OpenAPI spec URL above to build its 3D map.</p>
        )}
        {error && <p className="idle-hint idle-hint--error">{error}</p>}

        {workspace && (
          <Graph nodes={workspace.nodes} edges={workspace.edges} statuses={statuses} onSelect={setSelectedId} />
        )}
      </div>
      <DetailPanel node={selected} status={selectedId ? (statuses[selectedId] ?? 'unverified_no_schema') : 'unverified_no_schema'} onClose={handleClose} onSend={handleSend} />
    </div>
  )
}
```

- [ ] **Step 4: Handle the 501 gracefully in `frontend/src/components/DetailPanel.tsx`**

Read the current file first (Phase 0's version calls `onSend` and expects
a `SendResult` back). The backend now rejects every send with a 501 until
Phase 2 — `api.ts`'s `sendRequest` already throws on a non-2xx response
(its shared `json<T>` helper does this), so `handleSend` in `DetailPanel`
needs to catch that and show it as a real message rather than an
unhandled rejection. Update `handleSend`:

```tsx
async function handleSend() {
  setSending(true)
  setError(null)
  try {
    const r = await onSend(node!.id)
    setResult(r)
  } catch (e) {
    setError(String(e))
  } finally {
    setSending(false)
  }
}
```

Add an `error` state (`useState<string | null>(null)`, reset alongside
`result` in the existing node-change effect from Phase 0's fix wave), and
render it near the Send button:

```tsx
{error && <p className="dive__detail" style={{ color: 'var(--violate)' }}>{error}</p>}
```

- [ ] **Step 5: Add minimal CSS for the new form/idle states to `frontend/src/styles.css`**

```css
.workspace-form{margin-left:auto;display:flex;gap:8px;align-items:center}
.workspace-form input{background:rgba(255,255,255,.04);border:1px solid var(--hair);
  color:var(--paper);font-family:var(--mono);font-size:11px;padding:9px 12px;
  border-radius:2px}
.workspace-form input:first-of-type{width:160px}
.workspace-form input:last-of-type{width:320px}
.workspace-form button{background:transparent;border:1px solid var(--match);
  color:var(--match);font-family:var(--mono);font-size:10px;padding:9px 16px;
  border-radius:2px;cursor:pointer}
.workspace-form button:disabled{opacity:.5;cursor:not-allowed;border-color:var(--hair);color:var(--mute)}
.idle-hint{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  font-family:var(--mono);font-size:12px;color:var(--mute);padding:0 28px;text-align:center}
.idle-hint--error{color:var(--violate)}
```

- [ ] **Step 6: Typecheck**

Run: `cd frontend && npx tsc -b`
Expected: clean.

- [ ] **Step 7: Live-verify the full real flow in a real browser**

Start the backend (`cd backend && docker compose up -d && DATABASE_URL="postgresql+psycopg://parity:parity@127.0.0.1:5441/parity" .venv/bin/uvicorn app.main:app --port 8123 &`) and frontend (`cd frontend && npm run dev`). Open the dev URL with your browser tools:
- Type a workspace name and `https://petstore3.swagger.io/api/v3/openapi.json` (the real, live public spec — this is a genuine network call to a real third-party server, not a fixture), submit.
- Confirm a real 3D graph renders with more than 10 nodes, grouped into visible clusters (pet/store/user).
- Click a node, confirm the detail panel shows its real declared schema (with `$ref`s already resolved — you should see real property names, not a `$ref` string).
- Click Send — confirm the panel shows the real 501 error message ("real request execution arrives in Phase 2"), not a crash or a fake result.

- [ ] **Step 8: Commit**

```bash
git add src/api.ts src/components/WorkspaceForm.tsx src/App.tsx src/components/DetailPanel.tsx src/styles.css
git commit -m "frontend: real create-workspace flow against a real OpenAPI URL, remove the Phase 0 fixture"
```

---

### Task 6: CI Postgres service, HANDOFF.md, final verification

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `HANDOFF.md`

- [ ] **Step 1: Add a Postgres service to the backend CI job**

Read the current `.github/workflows/ci.yml` first. Add a `services:` block
to the `backend` job (same shape as `loom`'s own `ci.yml`):

```yaml
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: parity
          POSTGRES_PASSWORD: parity
          POSTGRES_DB: parity
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    env:
      DATABASE_URL: postgresql+psycopg://parity:parity@127.0.0.1:5432/parity
```

Add this right after `defaults:` in the `backend` job, before `steps:`.
The `alembic upgrade head` step needs adding too, before `pytest -q`:
`- run: alembic upgrade head`.

- [ ] **Step 2: Run the full local suite one more time**

Run: `cd backend && .venv/bin/python -m pytest -q` — expect all passing.
Run: `cd frontend && npx vitest run && npx tsc -b && npx vite build` — expect all passing/clean.

- [ ] **Step 3: Update `HANDOFF.md`**

Append a new dated section (after the existing Phase 0 entry, don't
rewrite it) describing: real Postgres persistence + real OpenAPI parsing
now live, `$ref` resolution decision, the first-2xx-only response schema
simplification, the honest-501 send route, the real live-verification
against `https://petstore3.swagger.io/api/v3/openapi.json`, and that
GraphQL parsing (Phase 1b) is a separate, not-yet-started follow-up plan.
Keep it factual and specific, matching Phase 0's own HANDOFF.md style —
real test counts, real verified behavior, not aspirational language.

- [ ] **Step 4: Commit and push**

```bash
git add .github/workflows/ci.yml HANDOFF.md
git commit -m "chore: CI Postgres service + HANDOFF.md for Phase 1a"
git fetch origin
git log HEAD..origin/main --oneline   # confirm empty before pushing
git push origin main
```

- [ ] **Step 5: Confirm CI is green**

Run: `gh run list --repo MaXiMo000/parity --limit 1` then
`gh run watch <run-id> --repo MaXiMo000/parity --exit-status`
Expected: both `backend` and `frontend` jobs pass.
