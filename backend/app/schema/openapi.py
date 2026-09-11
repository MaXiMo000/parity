"""Real OpenAPI 3.x ingestion: fetch a real spec, validate it, flatten
its operations into node data with every `$ref` resolved inline.

Real fetched specs (tests/fixtures/petstore-openapi.json, the standard
Swagger Petstore example) use `$ref` for essentially every schema — a
node's declared_request_schema/declared_response_schema would be useless
to any consumer without also holding the whole document, so this resolves
every local `#/...` pointer before a node is ever built. Local pointers
only: no external file/URL refs (SPEC.md's own no-live-resolution
discipline extends here)."""

from __future__ import annotations

from typing import Any

import httpx
from openapi_spec_validator import validate

_HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


class OpenAPIFetchError(Exception):
    pass


class OpenAPIValidationError(Exception):
    pass


def fetch_spec(source: str) -> dict[str, Any]:
    """`source` is a URL. Raises OpenAPIFetchError on any network failure
    or unparseable body (JSON or YAML, real specs are published as either)."""
    try:
        resp = httpx.get(source, timeout=15.0, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise OpenAPIFetchError(f"could not reach {source}: {exc}") from exc
    if resp.status_code != 200:
        raise OpenAPIFetchError(f"{source} returned HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError:
        pass
    try:
        import yaml

        return yaml.safe_load(resp.text)
    except Exception as exc:  # noqa: BLE001 -- any YAML parse failure is a fetch-shaped failure here
        raise OpenAPIFetchError(f"{source} is neither valid JSON nor YAML") from exc


def _resolve_refs(node: Any, root: dict[str, Any], seen: frozenset[str] = frozenset()) -> Any:
    """Recursively replaces every local `$ref` pointer with the fragment
    it points to. `seen` guards against a genuinely recursive schema
    (e.g. a tree-shaped type referencing itself) turning into infinite
    recursion -- a ref already being resolved higher up the same branch
    is left as a pointer rather than expanded again."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/"):
            if ref in seen:
                return {"$ref": ref}  # break the cycle, leave the pointer
            target: Any = root
            for part in ref[2:].split("/"):
                target = target[part]
            return _resolve_refs(target, root, seen | {ref})
        return {k: _resolve_refs(v, root, seen) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve_refs(v, root, seen) for v in node]
    return node


def _first_2xx_response_schema(responses: dict[str, Any], spec: dict[str, Any]) -> dict | None:
    for status in sorted(responses):
        if status.startswith("2"):
            schema = responses[status].get("content", {}).get("application/json", {}).get("schema")
            return _resolve_refs(schema, spec) if schema is not None else None
    return None


def parse_openapi(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Returns a flat list of node dicts (no `id` -- the caller/DB assigns
    that), one per (path, method) operation. Raises OpenAPIValidationError
    if the spec doesn't validate as real OpenAPI 3.x."""
    try:
        validate(spec)
    except Exception as exc:  # noqa: BLE001 -- verified against the real library (2026-09-11): a
        # missing/unrecognized version key raises ValidatorDetectError, a
        # present-but-malformed spec raises OpenAPIValidationError -- the
        # two share no common base except Exception itself (confirmed via
        # their real __mro__), so this catches both deliberately rather
        # than guessing at one specific class or import path.
        raise OpenAPIValidationError(f"not a valid OpenAPI document: {exc}") from exc

    nodes: list[dict[str, Any]] = []
    for path, path_item in spec.get("paths", {}).items():
        for method in _HTTP_METHODS:
            op = path_item.get(method)
            if op is None:
                continue
            operation_id = op.get("operationId") or f"{method}_{path}".replace("/", "_").replace("{", "").replace("}", "")
            request_schema = None
            body = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
            if body is not None:
                request_schema = _resolve_refs(body, spec)
            response_schema = _first_2xx_response_schema(op.get("responses", {}), spec)

            nodes.append({
                "kind": "rest_operation",
                "method": method.upper(),
                "path_template": path,
                "operation_id": operation_id,
                "type_name": None,
                "field_name": None,
                "declared_request_schema": request_schema,
                "declared_response_schema": response_schema,
            })
    return nodes
