"""Validates a real GraphQL response against a node's declared return
type (SPEC.md §6 step 7, GraphQL side; §13's "lighter custom shape-check"
option, chosen over graphql-core's execution-result validation machinery
-- that needs real resolvers this project doesn't have). Checks scalar
leaf types precisely and null-appropriateness at every level; a custom
object/enum type is only checked for presence and null-appropriateness,
not deep-validated field-by-field, since declared_response_schema only
stores that field's own return-type descriptor (Phase 1b), not a full
recursive schema of the type it names -- a real, stated v1 scope
boundary, not silently implied as deeper than it is."""

from __future__ import annotations

import json
from typing import Any

_SCALAR_CHECKS = {
    "Int": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "Float": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "String": lambda v: isinstance(v, str),
    "ID": lambda v: isinstance(v, str) or isinstance(v, int),
    "Boolean": lambda v: isinstance(v, bool),
}


def _check_type_shape(value: Any, descriptor: dict[str, Any], path: str) -> str | None:
    if value is None:
        if descriptor.get("nullable", True):
            return None
        return f"{path}: null is not allowed (declared non-nullable)"
    kind = descriptor["kind"]
    if kind == "LIST":
        if not isinstance(value, list):
            return f"{path}: expected a list, got {type(value).__name__}"
        for i, item in enumerate(value):
            detail = _check_type_shape(item, descriptor["of"], f"{path}[{i}]")
            if detail:
                return detail
        return None
    name = descriptor.get("name")
    check = _SCALAR_CHECKS.get(name)
    if check is not None and not check(value):
        return f"{path}: expected {name}, got {type(value).__name__}"
    return None


def check_graphql_drift(declared_response_schema: dict[str, Any] | None, response_body_text: str | None) -> tuple[str, str | None]:
    """Returns (status, detail). status is one of "matched", "violated",
    or "unverified_no_schema" (no declared schema to check against)."""
    if declared_response_schema is None:
        return "unverified_no_schema", None
    try:
        payload = json.loads(response_body_text) if response_body_text else None
    except ValueError:
        return "violated", "response body is not valid JSON"
    if not isinstance(payload, dict):
        return "violated", "response body is not a JSON object"
    if payload.get("errors"):
        return "violated", f"response contained GraphQL errors: {payload['errors']}"
    data = payload.get("data")
    if not isinstance(data, dict) or not data:
        return "violated", "response has no 'data' field to check"
    field_name, value = next(iter(data.items()))
    detail = _check_type_shape(value, declared_response_schema, f"data.{field_name}")
    if detail:
        return "violated", detail
    return "matched", None
