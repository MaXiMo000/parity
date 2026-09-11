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
from app.schema.graphql import GraphQLFetchError, GraphQLValidationError, fetch_introspection, parse_graphql
from app.schema.openapi import OpenAPIFetchError, OpenAPIValidationError, extract_base_path, fetch_spec, parse_openapi

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.post("", status_code=201)
def create_workspace(body: dict, session: Session = Depends(get_session)) -> dict:
    name = body.get("name")
    schema_kind = body.get("schema_kind")
    url = body.get("schema_source_url")
    raw = body.get("raw_schema")
    if not name or schema_kind not in ("openapi", "graphql"):
        raise HTTPException(status_code=422, detail="name and schema_kind in ('openapi', 'graphql') are required")
    if bool(url) == bool(raw):
        raise HTTPException(status_code=422, detail="exactly one of schema_source_url or raw_schema is required")

    base_path = ""
    if schema_kind == "openapi":
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
        base_path = extract_base_path(spec)
    else:
        if url:
            try:
                spec = fetch_introspection(url)
            except GraphQLFetchError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
        else:
            if not isinstance(raw, str):
                raise HTTPException(
                    status_code=422, detail="raw_schema for schema_kind='graphql' must be an SDL string"
                )
            spec = raw
        try:
            parsed_nodes = parse_graphql(spec)
        except GraphQLValidationError as exc:
            raise HTTPException(status_code=422, detail=f"invalid GraphQL schema: {exc}") from exc

    workspace = Workspace(
        user_id=DEFAULT_USER_ID, name=name, schema_kind=schema_kind,
        schema_source=url or "pasted", raw_schema=spec, base_path=base_path,
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
    edges = compute_rest_edges([
        {"id": n["id"], "path_template": n["path_template"]}
        for n in node_dicts if n["path_template"] is not None
    ])

    return {
        "id": workspace.id, "name": workspace.name, "schema_kind": workspace.schema_kind,
        "base_path": workspace.base_path, "schema_source": workspace.schema_source,
        "nodes": node_dicts,
        "edges": [{"from_node": a, "to_node": b} for a, b in edges],
    }
