"""POST/GET /api/workspaces — real Phase 1 behavior: fetches or accepts a
real OpenAPI spec, parses it for real (app/schema/openapi.py), persists
workspace+nodes to real Postgres. Replaces Phase 0's fixture routes
entirely."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, get_owned_workspace, require_csrf
from app.crypto import encrypt_credential
from app.db import get_session
from app.edges import compute_rest_edges
from app.graphql_edges import compute_graphql_edges
from app.models import Node, User, Workspace
from app.ratelimit import limiter
from app.schemas import CreateWorkspaceRequest, SetCredentialRequest
from app.schema.graphql import GraphQLFetchError, GraphQLValidationError, fetch_introspection, parse_graphql
from app.schema.openapi import OpenAPIFetchError, OpenAPIValidationError, extract_base_path, fetch_spec, parse_openapi

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.post("", status_code=201, dependencies=[Depends(require_csrf)])
# 10/minute: this route fetches a real remote schema URL on the caller's
# behalf (2026-09-18 security-hardening plan) -- the same "backend fires
# real outbound traffic" abuse shape as the request-proxy route below.
@limiter.limit("10/minute")
def create_workspace(request: Request, payload: CreateWorkspaceRequest, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)) -> dict:
    name = payload.name
    schema_kind = payload.schema_kind
    url = payload.schema_source_url
    raw = payload.raw_schema

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
        user_id=current_user.id, name=name, schema_kind=schema_kind,
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
def list_workspaces(session: Session = Depends(get_session), current_user: User = Depends(get_current_user)) -> list[dict]:
    rows = session.query(Workspace).filter(Workspace.user_id == current_user.id).all()
    return [{"id": w.id, "name": w.name, "schema_kind": w.schema_kind} for w in rows]


@router.get("/{workspace_id}")
def get_workspace(workspace_id: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)) -> dict:
    workspace = get_owned_workspace(workspace_id, current_user, session)

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
    virtual_nodes: list[dict] = []
    if workspace.schema_kind == "graphql":
        # REST's own edges list stays untouched (compute_rest_edges above
        # produces nothing for GraphQL nodes, since none of them carry a
        # path_template) -- this only ever adds a new, parallel path.
        graphql_edges, virtual_nodes = compute_graphql_edges([
            {"id": n["id"], "type_name": n["type_name"], "field_name": n["field_name"],
             "declared_response_schema": n["declared_response_schema"]}
            for n in node_dicts
        ])
        edges = [*edges, *graphql_edges]

    return {
        "id": workspace.id, "name": workspace.name, "schema_kind": workspace.schema_kind,
        "base_path": workspace.base_path, "schema_source": workspace.schema_source,
        "has_credential": workspace.encrypted_credential is not None,
        "credential_header_name": workspace.credential_header_name,
        "nodes": node_dicts,
        "edges": [{"from_node": a, "to_node": b} for a, b in edges],
        "virtual_nodes": virtual_nodes,
    }


@router.put("/{workspace_id}/credential", dependencies=[Depends(require_csrf)])
def set_credential(workspace_id: str, payload: SetCredentialRequest, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)) -> dict:
    workspace = get_owned_workspace(workspace_id, current_user, session)
    workspace.credential_header_name = payload.header_name
    workspace.encrypted_credential = encrypt_credential(payload.value)
    session.commit()
    return {"status": "ok"}


@router.delete("/{workspace_id}/credential", dependencies=[Depends(require_csrf)])
def clear_credential(workspace_id: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)) -> dict:
    workspace = get_owned_workspace(workspace_id, current_user, session)
    workspace.credential_header_name = None
    workspace.encrypted_credential = None
    session.commit()
    return {"status": "ok"}
