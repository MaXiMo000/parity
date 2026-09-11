"""Validates a real response against a REST node's declared response
schema (SPEC.md §6 step 7, §7.5's drift_finding.status enum): a real
jsonschema check against real JSON Schema (openapi.py's $ref-resolved
output), not a hand-rolled shape comparison."""

from __future__ import annotations

import json
from typing import Any

import jsonschema


def check_rest_drift(declared_response_schema: dict[str, Any] | None, response_body_text: str | None) -> tuple[str, str | None]:
    """Returns (status, detail). status is one of "matched", "violated",
    or "unverified_no_schema" (no declared schema exists to check
    against -- the node has no schema information for the response it
    actually got, so there's nothing to compare). Returning
    "unverified_no_match" is the caller's job, for when no node matched
    at all -- this function is only ever called once a node IS known."""
    if declared_response_schema is None:
        return "unverified_no_schema", None
    try:
        body: Any = json.loads(response_body_text) if response_body_text else None
    except ValueError:
        return "violated", "response body is not valid JSON"
    try:
        jsonschema.validate(body, declared_response_schema)
    except jsonschema.ValidationError as exc:
        return "violated", f"{exc.json_path}: {exc.message}"
    except Exception as exc:  # noqa: BLE001 -- a malformed or unresolvable declared
        # schema (e.g. a dangling $ref left by openapi.py's _resolve_refs cycle
        # guard, or a real jsonschema.SchemaError) means there is nothing
        # usable to check the response against -- unverified_no_schema is the
        # honest outcome here, not a crash and not a guessed "violated"
        # (Phase 2a's final review, finding I2, reproduced with an ordinary
        # self-referencing schema).
        return "unverified_no_schema", f"declared schema could not be used: {exc}"
    return "matched", None
