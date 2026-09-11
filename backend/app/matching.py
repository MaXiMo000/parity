"""Matches a real fired request to the REST Node it corresponds to
(SPEC.md §6 step 6): method + path-template match, literal segments
beating a templated one at the same position -- verified against a real
ambiguity in the Petstore fixture (/pet/findByStatus, /pet/findByTags,
and /pet/{petId} are all real 2-segment GET paths under /pet; a naive
segment-count match alone would let /pet/{petId} wrongly claim a request
meant for /pet/findByStatus)."""

from __future__ import annotations

from urllib.parse import urlparse


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
