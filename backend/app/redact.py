"""Redacts sensitive header values before persisting a Request/Response
to Postgres (SPEC.md §7.5: "redacted before persisting, same discipline
as loom's carabiner/lockstep subprocess redaction"). The real value is
still used for the live request/response -- only the stored copy is
scrubbed."""

from __future__ import annotations

from app.proxy.ssrf_guard import SENSITIVE_HEADERS


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        key: ("[REDACTED]" if key.lower() in SENSITIVE_HEADERS else value)
        for key, value in headers.items()
    }
