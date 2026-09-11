"""REST edges for the 3D graph (SPEC.md §8.3's "tree/force-graph by path
and tag"): purely derived from path_template, never persisted -- nothing
here needs its own migration or table, it's recomputed whenever a
workspace's graph is served."""

from __future__ import annotations

from collections import defaultdict


def _resource_key(path_template: str) -> str:
    parts = [p for p in path_template.split("/") if p]
    return parts[0] if parts else "/"


def compute_rest_edges(nodes: list[dict]) -> list[tuple[str, str]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for n in nodes:
        groups[_resource_key(n["path_template"])].append(n)

    edges: list[tuple[str, str]] = []
    for group_nodes in groups.values():
        ordered = sorted(group_nodes, key=lambda n: len(n["path_template"]))
        for a, b in zip(ordered, ordered[1:]):
            edges.append((a["id"], b["id"]))
    return edges
