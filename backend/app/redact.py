"""Redacts sensitive header values before persisting a Request/Response
to Postgres (SPEC.md §7.5: "redacted before persisting, same discipline
as loom's carabiner/lockstep subprocess redaction"). The real value is
still used for the live request/response -- only the stored copy is
scrubbed."""

from __future__ import annotations

_SENSITIVE_HEADER_NAMES = {"authorization", "cookie", "set-cookie", "proxy-authorization", "x-api-key"}


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        key: ("[REDACTED]" if key.lower() in _SENSITIVE_HEADER_NAMES else value)
        for key, value in headers.items()
    }
