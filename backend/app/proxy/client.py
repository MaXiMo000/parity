"""The real outbound request-execution proxy (SPEC.md §6 step 5, §7.3):
fires a real HTTP request to a real target, through the same SSRF-pinned
guard every other outbound fetch in this backend uses."""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.proxy.ssrf_guard import send_pinned


class ProxyError(Exception):
    pass


def fire_request(method: str, url: str, headers: dict[str, str] | None, body: str | None) -> tuple[httpx.Response, int]:
    """Returns (response, latency_ms). Raises ProxyError on an
    unsafe/unresolvable target or a network failure (via send_pinned's
    own error handling)."""
    kwargs: dict[str, Any] = {}
    if headers:
        kwargs["headers"] = headers
    if body is not None:
        kwargs["content"] = body.encode("utf-8")
    start = time.monotonic()
    resp = send_pinned(method, url, ProxyError, **kwargs)
    latency_ms = int((time.monotonic() - start) * 1000)
    return resp, latency_ms
