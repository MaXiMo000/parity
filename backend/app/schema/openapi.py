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

import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

import httpx
from openapi_spec_validator import validate

_HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


class OpenAPIFetchError(Exception):
    pass


class OpenAPIValidationError(Exception):
    pass


def _resolve_safe_ip(hostname: str) -> str | None:
    """Resolves hostname and returns the first candidate IP to pin the
    real connection to, or None if resolution fails or ANY resolved
    address is not globally routable -- a hostname that round-robins
    between a safe and an unsafe address must not pass on a lucky first
    answer. `is_global` (verified 2026-09-11 against the real
    `ipaddress` stdlib module) correctly subsumes the old
    is_private/is_loopback/is_link_local/is_reserved checks AND
    additionally rejects CGNAT (100.64.0.0/10, RFC 6598) -- a real gap
    the old checks missed, since CGNAT is real internal space at several
    cloud providers."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return None
    ips = [info[4][0] for info in infos]
    if any(not ipaddress.ip_address(ip).is_global for ip in ips):
        return None
    return ips[0]


def _build_pinned_request(method: str, url: str, **kwargs: Any) -> httpx.Request | None:
    """Resolves and validates url's hostname via _resolve_safe_ip, then
    builds a real httpx.Request that connects directly to the validated
    IP -- closing the DNS-rebinding TOCTOU window between our own safety
    check and whatever httpx's own independent connection-time
    resolution would otherwise do. The original hostname is preserved as
    the Host header and the TLS SNI/certificate-hostname
    (extensions={"sni_hostname": ...}, verified against the real
    installed httpx 0.28.1, 2026-09-11) so the request is
    indistinguishable from an ordinary one to the target server. Returns
    None if the URL isn't http(s), has no hostname (e.g. a relative
    redirect Location -- rejected the same way the old is_safe_url
    rejected it), or the hostname doesn't resolve to an all-safe address
    set."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None
    hostname = parsed.hostname
    if not hostname:
        return None
    ip = _resolve_safe_ip(hostname)
    if ip is None:
        return None
    pinned_url = httpx.URL(url).copy_with(host=ip)
    headers = {**(kwargs.pop("headers", None) or {}), "Host": hostname}
    return httpx.Request(method, pinned_url, headers=headers, extensions={"sni_hostname": hostname}, **kwargs)


def send_pinned(method: str, url: str, error_cls: type[Exception], **kwargs: Any) -> httpx.Response:
    """Builds a pinned request (_build_pinned_request) and sends it,
    manually following at most one redirect hop -- the hop itself
    re-built and re-validated the same way, so an initially-safe URL
    that redirects to an internal address is still caught. Shared by
    fetch_spec (below) and fetch_introspection (app/schema/graphql.py)
    so both modules' fetch surfaces get identical SSRF-pinning behavior,
    not two independently-drifting copies. Raises error_cls (each
    module's own *FetchError) on an unsafe/unresolvable target or a
    network failure at either hop."""
    req = _build_pinned_request(method, url, **kwargs)
    if req is None:
        raise error_cls(f"{url} is not a permitted target")
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.send(req, follow_redirects=False)
    except httpx.HTTPError as exc:
        raise error_cls(f"could not reach {url}: {exc}") from exc
    if resp.is_redirect:
        location = resp.headers.get("location")
        redirect_req = _build_pinned_request(method, location, **kwargs) if location else None
        if redirect_req is None:
            raise error_cls(f"{url} redirected to a target that is not permitted")
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.send(redirect_req, follow_redirects=False)
        except httpx.HTTPError as exc:
            raise error_cls(f"could not reach {location}: {exc}") from exc
    return resp


def fetch_spec(source: str) -> dict[str, Any]:
    """`source` is a URL. Raises OpenAPIFetchError on any network
    failure, an unsafe/unresolvable target (at either the original URL
    or a redirect hop), a non-200 response, or an unparseable body (JSON
    or YAML, real specs are published as either)."""
    resp = send_pinned("GET", source, OpenAPIFetchError)
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
            # The response object itself can be a `$ref` (not just its nested
            # schema) -- resolve it before navigating into .content/.schema.
            response_obj = _resolve_refs(responses[status], spec)
            schema = response_obj.get("content", {}).get("application/json", {}).get("schema")
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
            # The requestBody itself can be a `$ref` (not just its nested
            # schema) -- resolve the object before navigating into it.
            request_body_obj = _resolve_refs(op.get("requestBody"), spec) if op.get("requestBody") else None
            body = (request_body_obj or {}).get("content", {}).get("application/json", {}).get("schema")
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
