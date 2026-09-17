"""POST /api/curl-parse -- no side effects, just parses (SPEC.md §7.6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.models import User
from app.proxy.curl_parser import CurlParseError, parse_curl
from app.schemas import CurlParseRequest

router = APIRouter(prefix="/api", tags=["curl"])


@router.post("/curl-parse")
def curl_parse_route(payload: CurlParseRequest, current_user: User = Depends(get_current_user)) -> dict:
    try:
        return parse_curl(payload.curl)
    except CurlParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
