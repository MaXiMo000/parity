"""Matches a real fired request to the REST Node it corresponds to
(SPEC.md §6 step 6): method + path-template match, literal segments
beating a templated one at the same position -- verified against a real
ambiguity in the Petstore fixture (/pet/findByStatus, /pet/findByTags,
and /pet/{petId} are all real 2-segment GET paths under /pet; a naive
segment-count match alone would let /pet/{petId} wrongly claim a request
meant for /pet/findByStatus)."""

from __future__ import annotations

import json
from urllib.parse import urlparse

from graphql import FieldNode, GraphQLSyntaxError, OperationDefinitionNode, parse


def same_declared_host(request_url: str, workspace_schema_source: str) -> bool:
    """The shared "does this request's real destination match the
    workspace's own declared API" check named as the single most
    significant carried-over gap since Phase 2b's own HANDOFF section:
    REST matching checked method+path shape only, and GraphQL matching
    (added that same phase) checked body shape only -- neither looked at
    *where* the request actually went, so a request aimed at an
    unrelated host could still match a node purely by path/body shape.

    `workspace_schema_source` is `Workspace.schema_source` -- a real URL
    when the workspace was created from one, or the literal string
    `"pasted"` when it was created from raw/uploaded schema text (no real
    source URL exists to compare against in that case). This is the same
    origin `frontend/src/components/RequestBuilder.tsx`'s own `guessUrl`
    already treats as the workspace's real API host for REST, and as the
    GraphQL endpoint itself for GraphQL -- reusing that existing
    assumption here, not inventing a new one.

    Stated honestly, not implied as more: this compares hostnames only
    (case-insensitive), not full origins (scheme/port), and when
    `workspace_schema_source` has no discernible host (the `"pasted"`
    case, or any raw-schema/SDL-paste workspace) this returns True --
    there is no real signal to check against, so it doesn't invent a
    false rejection. It is not a security boundary (the SSRF guard is);
    it is a correctness signal so a request to a clearly unrelated host
    doesn't get miscredited as verifying a node it was never sent to.
    """
    declared_host = urlparse(workspace_schema_source).hostname
    if not declared_host:
        return True
    request_host = urlparse(request_url).hostname
    if not request_host:
        return False
    return request_host.lower() == declared_host.lower()


def match_rest_node(nodes: list[dict], method: str, url: str, base_path: str) -> dict | None:
    """`nodes` are REST node dicts carrying at least `id`, `method`,
    `path_template`. `base_path` (Workspace.base_path) is stripped from
    the request's path before matching -- a real spec's declared paths
    are relative to its servers[0].url, not to the request's full path.
    Returns the best-matching node dict, or None if no node's template
    has the same segment count and (literal-or-template) shape as the
    request path."""
    path = urlparse(url).path
    if base_path and path.startswith(base_path):
        path = path[len(base_path):]
    path_segs = [s for s in path.strip("/").split("/") if s]

    best: dict | None = None
    best_score = -1
    for node in nodes:
        if node.get("method") is None or node["method"].upper() != method.upper():
            continue
        tmpl = node.get("path_template")
        if tmpl is None:
            continue
        tmpl_segs = [s for s in tmpl.strip("/").split("/") if s]
        if len(tmpl_segs) != len(path_segs):
            continue
        score = 0
        ok = True
        for tmpl_seg, path_seg in zip(tmpl_segs, path_segs):
            if tmpl_seg.startswith("{") and tmpl_seg.endswith("}"):
                continue
            if tmpl_seg == path_seg:
                score += 1
            else:
                ok = False
                break
        if ok and score > best_score:
            best = node
            best_score = score
    return best


def match_graphql_node(nodes: list[dict], request_body_text: str | None) -> dict | None:
    """Parses the real GraphQL-over-HTTP request body (the standard JSON
    envelope: {"query": "...", "variables": {...}}) and matches its
    operation type + first top-level selected field to a Node (SPEC.md
    §6 step 6, GraphQL side). `nodes` are GraphQL node dicts carrying at
    least `id`, `type_name`, `field_name`. Returns None -- never a guess
    -- if the body isn't valid JSON, has no string "query" field, the
    query doesn't parse as valid GraphQL, the document has no real
    operation definition, or no node matches. v1 scope: only the FIRST
    operation definition and its FIRST top-level field selection are
    considered (SPEC.md's own stated simplification for the common
    single-operation, single-field case)."""
    if not request_body_text:
        return None
    try:
        envelope = json.loads(request_body_text)
    except ValueError:
        return None
    query_text = envelope.get("query") if isinstance(envelope, dict) else None
    if not isinstance(query_text, str):
        return None
    try:
        document = parse(query_text)
    except GraphQLSyntaxError:
        return None
    for definition in document.definitions:
        if not isinstance(definition, OperationDefinitionNode):
            continue
        type_name = definition.operation.value.capitalize()  # "query" -> "Query", "mutation" -> "Mutation"
        if not definition.selection_set.selections:
            return None
        first_selection = definition.selection_set.selections[0]
        if not isinstance(first_selection, FieldNode):
            return None
        field_name_node = getattr(first_selection, "name", None)
        if field_name_node is None:
            return None
        field_name = field_name_node.value
        for node in nodes:
            if node.get("type_name") == type_name and node.get("field_name") == field_name:
                return node
        return None
    return None
