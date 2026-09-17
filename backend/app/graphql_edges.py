"""GraphQL edges for the 3D graph (SPEC.md §8.3's "graph by type
relationships -- Query and Mutation as roots, fields fanning out to the
types they return"): purely derived from each node's own type_name and
declared_response_schema, never persisted -- same "recomputed on every
serve" discipline as app/edges.py's REST path, applied to GraphQL's own
shape.

Only root-type fields exist as real Node rows (Phase 1b's own stated
scope -- a returned type's own fields are never parsed or stored), so
there is no real Node to represent e.g. the "Country" type itself. This
module fills that gap with synthetic, non-persisted "hub" nodes: one per
root (Query/Mutation) and one per distinct *non-scalar* return type. A
scalar-returning field (String/Int/Float/ID/Boolean) gets an edge to its
root hub only -- two fields that both happen to return a bare String
aren't actually related the way two fields both returning the custom
object type Pet are, and a shared-scalar hub would become a meaningless
high-degree hairball connecting unrelated fields."""

from __future__ import annotations

_SCALARS = frozenset({"String", "Int", "Float", "ID", "Boolean"})


def _leaf_type_name(descriptor: dict | None) -> str | None:
    """Unwraps a declared_response_schema type descriptor (app/schema/
    graphql.py's _describe_type shape) through any LIST nesting down to
    its real NAMED type name."""
    while descriptor and descriptor.get("kind") == "LIST":
        descriptor = descriptor.get("of")
    return (descriptor or {}).get("name")


def compute_graphql_edges(nodes: list[dict]) -> tuple[list[tuple[str, str]], list[dict]]:
    """`nodes`: dicts carrying at least id/type_name/field_name/
    declared_response_schema (GraphQL Node dicts). Returns (edges,
    virtual_nodes). Hub ids are deterministic ("root:Query", "type:Pet")
    -- stable across repeated calls for the same workspace so the
    frontend's force layout doesn't reshuffle hub identity on refetch."""
    edges: list[tuple[str, str]] = []
    virtual_nodes: list[dict] = []
    seen: set[str] = set()

    for n in nodes:
        type_name = n.get("type_name")
        if type_name is None:
            continue
        root_id = f"root:{type_name}"
        if root_id not in seen:
            virtual_nodes.append({"id": root_id, "label": type_name, "kind": "graphql_root"})
            seen.add(root_id)
        edges.append((root_id, n["id"]))

        leaf = _leaf_type_name(n.get("declared_response_schema"))
        if leaf and leaf not in _SCALARS:
            type_id = f"type:{leaf}"
            if type_id not in seen:
                virtual_nodes.append({"id": type_id, "label": leaf, "kind": "graphql_type"})
                seen.add(type_id)
            edges.append((n["id"], type_id))

    return edges, virtual_nodes
