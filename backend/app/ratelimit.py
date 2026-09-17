"""Shared in-memory rate limiter (2026-09-18 security-hardening plan).
In-memory, not Redis-backed: this deploy's own real topology (render.yaml)
is one Render web-service instance, no distributed cache -- an in-memory
limiter is the correct choice for that shape, not a corner cut. Revisit
only if the topology ever becomes multi-instance.

Keyed by the real logged-in user id when a session exists, falling back
to remote address for anonymous requests (the login/callback routes
themselves, which run before any session exists) -- several users behind
one shared IP (a NAT, an office network) should not throttle each other
once each is logged in as themselves."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def rate_limit_key(request: Request) -> str:
    user_id = request.session.get("user_id") if hasattr(request, "session") else None
    return f"user:{user_id}" if user_id else get_remote_address(request)


limiter = Limiter(key_func=rate_limit_key)
