"""Real request execution (SPEC.md §6 steps 4-8, §7.6): fires a real
request through the SSRF-guarded proxy, matches it to a known REST or
GraphQL Node, validates the real response against that node's declared
schema, and persists Request/Response/DriftFinding with headers redacted
before storage. Replaces Phase 0/1's honest 501 entirely."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, get_owned_workspace
from app.db import get_session
from app.drift.graphql import check_graphql_drift
from app.drift.rest import check_rest_drift
from app.matching import match_graphql_node, match_rest_node
from app.models import DriftFinding, Node, Request, Response, User, Workspace
from app.proxy.client import ProxyError, fire_request
from app.redact import redact_headers

router = APIRouter(prefix="/api/workspaces", tags=["requests"])


def _safe_json(text: str | None) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text


@router.post("/{workspace_id}/requests", status_code=201)
def send_request(workspace_id: str, body: dict, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)) -> dict:
    workspace = get_owned_workspace(workspace_id, current_user, session)

    method = body.get("method")
    url = body.get("url")
    headers = body.get("headers") or {}
    req_body = body.get("body")
    if not method or not url:
        raise HTTPException(status_code=422, detail="method and url are required")
    if req_body is not None and not isinstance(req_body, str):
        raise HTTPException(status_code=422, detail="body must be a string or null")

    try:
        resp, latency_ms = fire_request(method, url, headers, req_body)
    except ProxyError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    node: Node | None = None
    if workspace.schema_kind == "openapi":
        node_dicts = [
            {"id": n.id, "method": n.method, "path_template": n.path_template}
            for n in workspace.nodes
        ]
        matched = match_rest_node(node_dicts, method, url, workspace.base_path)
        if matched:
            node = session.get(Node, matched["id"])
    elif workspace.schema_kind == "graphql":
        graphql_node_dicts = [
            {"id": n.id, "type_name": n.type_name, "field_name": n.field_name}
            for n in workspace.nodes
        ]
        graphql_matched = match_graphql_node(graphql_node_dicts, req_body)
        if graphql_matched:
            node = session.get(Node, graphql_matched["id"])

    request_row = Request(
        workspace_id=workspace.id, node_id=node.id if node else None,
        method=method.upper(), url=url, headers=redact_headers(headers), body=req_body,
    )
    session.add(request_row)
    session.flush()

    response_row = Response(
        request_id=request_row.id, status_code=resp.status_code,
        headers=redact_headers(dict(resp.headers)), body=resp.text, latency_ms=latency_ms,
    )
    session.add(response_row)
    session.flush()

    if node is not None:
        node.call_count += 1
        if resp.status_code == 204:
            status, detail = "unverified_no_schema", "204 No Content has no body to validate against a declared schema"
        elif not (200 <= resp.status_code < 300):
            status, detail = "unverified_no_schema", f"non-2xx response ({resp.status_code}); only 2xx response schemas are declared (SPEC.md §7.2)"
        elif node.kind == "graphql_field":
            status, detail = check_graphql_drift(node.declared_response_schema, resp.text)
        else:
            status, detail = check_rest_drift(node.declared_response_schema, resp.text)
    else:
        status, detail = "unverified_no_match", None

    drift_row = DriftFinding(response_id=response_row.id, node_id=node.id if node else None, status=status, detail=detail)
    session.add(drift_row)
    session.commit()

    return {
        "request": {"id": request_row.id, "node_id": request_row.node_id, "method": request_row.method, "url": request_row.url},
        "response": {"id": response_row.id, "status_code": response_row.status_code, "body": _safe_json(resp.text), "latency_ms": latency_ms},
        "drift_finding": {"id": drift_row.id, "status": drift_row.status, "detail": drift_row.detail},
    }


@router.get("/{workspace_id}/requests")
def list_requests(workspace_id: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)) -> list[dict]:
    workspace = get_owned_workspace(workspace_id, current_user, session)
    rows = (
        session.query(Request)
        .filter(Request.workspace_id == workspace_id)
        .order_by(Request.sent_at.desc())
        .all()
    )
    return [
        {"id": r.id, "node_id": r.node_id, "method": r.method, "url": r.url, "sent_at": r.sent_at.isoformat()}
        for r in rows
    ]


@router.get("/{workspace_id}/nodes/{node_id}/history")
def node_history(workspace_id: str, node_id: str, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)) -> list[dict]:
    get_owned_workspace(workspace_id, current_user, session)  # 404s before even checking the node exists, if the workspace isn't the caller's
    try:
        uuid.UUID(node_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown node id")
    node = session.get(Node, node_id)
    if node is None or node.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="unknown node id")
    rows = (
        session.query(DriftFinding)
        .filter(DriftFinding.node_id == node_id)
        .order_by(DriftFinding.created_at.desc())
        .all()
    )
    return [
        {"id": f.id, "status": f.status, "detail": f.detail, "created_at": f.created_at.isoformat()}
        for f in rows
    ]
