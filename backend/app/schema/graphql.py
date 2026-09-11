"""Real GraphQL ingestion: live introspection over HTTP, or a pasted SDL
document, both producing the same flat node list Postgres persists. Mirrors
app/schema/openapi.py's shape (fetch/parse, one Node per operation) applied
to GraphQL's own shape: one Node per field reachable from Query/Mutation
(SPEC.md §7.2 — Subscription is a different, streaming transport shape,
out of scope for v1)."""

from __future__ import annotations

from typing import Any

import httpx
from graphql import (
    GraphQLList,
    GraphQLNonNull,
    build_client_schema,
    build_schema,
    get_introspection_query,
)

from app.schema.openapi import is_safe_url

_ROOT_TYPES = ("Query", "Mutation")


class GraphQLFetchError(Exception):
    pass


class GraphQLValidationError(Exception):
    pass


def fetch_introspection(source: str) -> dict[str, Any]:
    """`source` is a GraphQL endpoint URL. POSTs the standard introspection
    query and returns its `data` payload -- the same shape `parse_graphql`
    accepts directly. Reuses openapi.py's `is_safe_url` (same SSRF-baseline
    reasoning, SPEC.md §7.3, applied to this new fetch surface) and follows
    at most one redirect hop manually, re-checked, matching fetch_spec's
    own pattern."""
    if not is_safe_url(source):
        raise GraphQLFetchError(f"{source} is not a permitted target")
    body = {"query": get_introspection_query()}
    try:
        resp = httpx.post(source, json=body, timeout=15.0, follow_redirects=False)
    except httpx.HTTPError as exc:
        raise GraphQLFetchError(f"could not reach {source}: {exc}") from exc
    if resp.is_redirect:
        location = resp.headers.get("location")
        if not location or not is_safe_url(location):
            raise GraphQLFetchError(f"{source} redirected to a target that is not permitted")
        try:
            resp = httpx.post(location, json=body, timeout=15.0, follow_redirects=False)
        except httpx.HTTPError as exc:
            raise GraphQLFetchError(f"could not reach {location}: {exc}") from exc
    if resp.status_code != 200:
        raise GraphQLFetchError(f"{source} returned HTTP {resp.status_code}")
    try:
        payload = resp.json()
    except ValueError as exc:
        raise GraphQLFetchError(f"{source} did not return valid JSON") from exc
    if not isinstance(payload, dict):
        raise GraphQLFetchError(f"{source} did not return a JSON object")
    if payload.get("errors"):
        raise GraphQLFetchError(f"{source} returned GraphQL errors: {payload['errors']}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise GraphQLFetchError(f"{source} returned no introspection data")
    return data


def _describe_type(t: Any) -> dict[str, Any]:
    """Flattens a graphql-core type object into a small JSON-safe shape:
    {"kind": "NAMED", "name": "...", "nullable": bool} or, for a list,
    {"kind": "LIST", "of": <nested>, "nullable": bool}. NonNull unwraps to
    its inner type with nullable=False -- verified against the real
    library (2026-09-11): GraphQLNonNull never wraps another GraphQLNonNull,
    so one unwrap per level is exact, not an approximation."""
    if isinstance(t, GraphQLNonNull):
        inner = _describe_type(t.of_type)
        inner["nullable"] = False
        return inner
    if isinstance(t, GraphQLList):
        return {"kind": "LIST", "of": _describe_type(t.of_type), "nullable": True}
    return {"kind": "NAMED", "name": t.name, "nullable": True}


def parse_graphql(schema_input: dict[str, Any] | str) -> list[dict[str, Any]]:
    """`schema_input` is either a pasted SDL document (str) or an
    introspection result's `data` payload (dict, e.g. fetch_introspection's
    return value). Returns a flat list of node dicts, one per field
    reachable from Query or Mutation (Subscription out of scope, SPEC.md
    §7.2). Raises GraphQLValidationError if the input doesn't build into a
    real schema."""
    try:
        schema = (
            build_schema(schema_input)
            if isinstance(schema_input, str)
            else build_client_schema(schema_input)
        )
    except Exception as exc:  # noqa: BLE001 -- verified against the real library (2026-09-11):
        # build_schema raises GraphQLSyntaxError on bad SDL; build_client_schema
        # raises TypeError on a malformed payload and KeyError on one missing
        # required keys (e.g. no "types" list) -- three types sharing no
        # common base except Exception itself (confirmed via their real
        # __mro__), so this catches all three deliberately rather than
        # guessing at one specific class or import path.
        raise GraphQLValidationError(f"not a valid GraphQL schema: {exc}") from exc

    nodes: list[dict[str, Any]] = []
    for type_name in _ROOT_TYPES:
        root_type = getattr(schema, f"{type_name.lower()}_type", None)
        if root_type is None:
            continue
        for field_name, field in root_type.fields.items():
            args_schema = (
                {arg_name: _describe_type(arg.type) for arg_name, arg in field.args.items()}
                if field.args
                else None
            )
            nodes.append({
                "kind": "graphql_field",
                "method": None,
                "path_template": None,
                "operation_id": None,
                "type_name": type_name,
                "field_name": field_name,
                "declared_request_schema": args_schema,
                "declared_response_schema": _describe_type(field.type),
            })
    return nodes
