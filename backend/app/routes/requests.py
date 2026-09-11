"""Real request execution (SPEC.md §6 steps 4-8, §7.6): fires a real
request through the SSRF-guarded proxy, matches it to a known REST Node
(GraphQL matching arrives in Phase 2b -- until then a GraphQL workspace's
requests are honestly unverified_no_match, never guessed), validates the
real response against that node's declared schema, and persists
Request/Response/DriftFinding with headers redacted before storage.
Replaces Phase 0/1's honest 501 entirely."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.drift.rest import check_rest_drift
from app.matching import match_rest_node
from app.models import DriftFinding, Node, Request, Response, Workspace
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
def send_request(workspace_id: str, body: dict, session: Session = Depends(get_session)) -> dict:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="unknown workspace id")

    method = body.get("method")
    url = body.get("url")
    headers = body.get("headers") or {}
    req_body = body.get("body")
    if not method or not url:
        raise HTTPException(status_code=422, detail="method and url are required")

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
def list_requests(workspace_id: str, session: Session = Depends(get_session)) -> list[dict]:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="unknown workspace id")
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
def node_history(workspace_id: str, node_id: str, session: Session = Depends(get_session)) -> list[dict]:
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
