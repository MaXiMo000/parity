"""Rejects any request whose declared Content-Length exceeds MAX_BODY_BYTES
before its body is ever read into memory (2026-09-18 security-hardening
plan: closes the "no request-body size cap on parity's own API" gap --
every route previously accepted an unbounded body/headers payload).

Stated honestly, not implied as more: this checks the declared
Content-Length header only, not a running byte count of what's actually
received -- a client that lies about Content-Length and streams more
than it declared is a different, transport-level concern (chunked
transfer-encoding with no Content-Length at all bypasses this check
entirely). Real browsers always set a real Content-Length for the
JSON.stringify bodies this frontend sends, so this closes the realistic
case; a fully byte-accurate streaming cap would be real, larger, separate
work."""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

MAX_BODY_BYTES = 2 * 1024 * 1024  # 2 MiB -- generous for any real curl-pasted request/response this tool handles, small enough to bound abuse


class MaxBodySizeMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            content_length = Headers(scope=scope).get("content-length")
            if content_length is not None:
                try:
                    length = int(content_length)
                except ValueError:
                    length = None
                if length is not None and length > self.max_bytes:
                    response = JSONResponse(
                        {"detail": f"request body exceeds the {self.max_bytes}-byte limit"},
                        status_code=413,
                    )
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)
