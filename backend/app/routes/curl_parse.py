"""POST /api/curl-parse -- no side effects, just parses (SPEC.md §7.6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.models import User
from app.proxy.curl_parser import CurlParseError, parse_curl

router = APIRouter(prefix="/api", tags=["curl"])


@router.post("/curl-parse")
def curl_parse_route(body: dict, current_user: User = Depends(get_current_user)) -> dict:
    curl = body.get("curl")
    if not isinstance(curl, str) or not curl.strip():
        raise HTTPException(status_code=422, detail="curl is required")
    try:
        return parse_curl(curl)
    except CurlParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
