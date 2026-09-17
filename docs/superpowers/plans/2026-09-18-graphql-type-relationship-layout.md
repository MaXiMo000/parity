# GraphQL Type-Relationship 3D Layout — Design Plan

**Status:** planned, not started. Written 2026-09-18 in response to a direct
request for a plan (not an implementation) for the last named v1-scope gap:
"GraphQL nodes render with no edges" (carried since Phase 1b's own HANDOFF
entry, confirmed still open through Phase 3c and the 2026-09-17 backlog
session). This is real layout/design work — it needs a data-model decision
(what an "edge" even means for GraphQL, since there's no `path_template` to
derive one from) and a rendering decision (what a non-endpoint "type" looks
like next to real, clickable endpoint nodes) — not a one-line fix, which is
why it was deliberately left out of the backlog session that closed the
other two carried-over gaps (node sizing, host-blind matching).

**Goal:** SPEC.md §8.3: *"GraphQL mode: a graph by type relationships —
Query and Mutation as roots, fields fanning out to the types they return."*
Give GraphQL workspaces a real edge-connected 3D graph reusing the existing
REST rendering machinery (`Graph.tsx`/`layout.ts`/`Edge.tsx` are already
fully generic over any `{id, x, y, z}` node list and `{from_node, to_node}`
edge list — built for REST edges, but nothing in them is REST-specific).

**Spec:** `SPEC.md` §8.3 (the exact quoted design), §7.5 (`Node.type_name`/
`field_name`/`declared_response_schema` — the only GraphQL data that exists
today to build a layout from; no schema change needed for this plan's core
idea).

## The data problem this plan has to solve

Phase 1b's own stated scope (`HANDOFF.md`, "Known simplifications"): only
`Query`/`Mutation` root-type fields become `Node` rows. A field's return
type (e.g. `Country`) is captured only as a *descriptor* on that field's own
`declared_response_schema` — the `Country` type's own fields are never
parsed or stored as anything. So SPEC's literal picture — "Query and
Mutation as roots, fields fanning out to the types they return" — cannot be
built from real `Node` rows alone: there is no `Node` row representing the
`Country` type to fan out *to*. Two ways to resolve that gap:

- **(A) Shared-return-type clustering.** Connect two field-`Node`s directly
  to each other if they declare the same return type name (e.g. `pet(id)`
  and `pets` both returning `Pet` get an edge between them). No new node
  concept, minimal code, reuses 100% of the existing rendering path
  unchanged. Downside: doesn't produce the literal "roots fan out to types"
  picture SPEC describes — it produces "fields that share a type drift
  toward each other," a real but different signal.
- **(B) Synthetic root/type hub nodes (recommended).** Introduce
  non-persisted, view-only "hub" nodes: one per root (`Query`, `Mutation`)
  and one per distinct *non-scalar* return type name a field declares.
  Real field-`Node`s get an edge to their root hub AND an edge to their
  return-type hub. This is the literal SPEC picture — roots fan out to
  fields, fields fan out to the types they return — and it's honestly
  achievable without parsing a single additional GraphQL type, because a
  hub only needs a name, not its own fields.

**Recommendation: (B).** It's the design SPEC actually describes, it's not
meaningfully more backend work than (A) (see Task 1's real code below), and
it gives GraphQL mode a genuine visual identity distinct from REST's
resource-tree clustering — which SPEC.md §8.3's "dual-mode, sharing one
visual language" framing asks for (same rendering *language*, different
graph *shape*).

**A scope cut (B) must make explicitly, not silently:** scalar return types
(`String`, `Int`, `Float`, `ID`, `Boolean`) must NOT get a shared hub — two
fields that both happen to return a bare `String` are not "related" the way
two fields both returning the custom object type `Pet` are. A shared-scalar
hub would become a meaningless high-degree hairball connecting unrelated
fields. Scalar-returning fields get an edge to their root hub only, never a
type hub.

## Task 1: Backend — `compute_graphql_edges` + virtual hub nodes

**Files:**
- Create: `backend/app/graphql_edges.py` (parallel to the existing
  `app/edges.py` for REST — same "purely derived, never persisted,
  recomputed on every serve" discipline)
- Modify: `backend/app/routes/workspaces.py` (`get_workspace`: call the new
  function for `schema_kind == "graphql"`, merge its output into the
  response as a new top-level `virtual_nodes` array — kept separate from
  `nodes`, not merged into it, because a hub is not a real, sendable API
  operation and must never be reachable through the same click → detail →
  Send path a real node is; conflating the two lists risks a user opening
  a request builder against a "type," which isn't a thing)
- Test: `backend/tests/test_graphql_edges.py`

**Core logic** (real, not pseudocode — this is what Task 1 implements):

```python
_SCALARS = {"String", "Int", "Float", "ID", "Boolean"}

def _leaf_type_name(descriptor: dict | None) -> str | None:
    while descriptor and descriptor.get("kind") == "LIST":
        descriptor = descriptor.get("of")
    return (descriptor or {}).get("name")

def compute_graphql_edges(nodes: list[dict]) -> tuple[list[tuple[str, str]], list[dict]]:
    """`nodes`: dicts with id/type_name/field_name/declared_response_schema.
    Returns (edges, virtual_nodes). Deterministic ids ("root:Query",
    "type:Pet") -- stable across repeated calls for the same workspace so
    the frontend's force layout doesn't reshuffle hub identity on refetch."""
    edges: list[tuple[str, str]] = []
    virtual_nodes: list[dict] = []
    seen: set[str] = set()

    for n in nodes:
        root_id = f"root:{n['type_name']}"  # "root:Query" / "root:Mutation"
        if root_id not in seen:
            virtual_nodes.append({"id": root_id, "label": n["type_name"], "kind": "graphql_root"})
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
```

- [ ] Write `app/graphql_edges.py` with the function above.
- [ ] Wire into `get_workspace`: for `schema_kind == "graphql"`, call it with
      the same node-dict shape `edges.py`'s REST path already builds; merge
      its edge tuples into the existing `edges` list in the response, and
      add its virtual nodes under a new `"virtual_nodes"` key (empty list
      for `schema_kind == "openapi"` — REST responses get the key too, for
      one consistent response shape the frontend can rely on without an
      `undefined` check).
- [ ] Tests: real fixtures, not synthetic edge cases picked to look nice —
      reuse this project's own `countries.trevorblades.com` GraphQL schema
      shape (already the project's standard GraphQL fixture, per every
      prior phase's HANDOFF live-verification). Cover: two fields sharing a
      custom-object return type get a shared type hub; a scalar-returning
      field gets no type hub (only its root edge); `Query` and `Mutation`
      fields get separate root hubs when a schema has both; hub ids are
      stable across two calls with the same input (`==`, not just
      structurally equal).

## Task 2: Frontend — render hub nodes with their own honest visual identity

**Files:**
- Modify: `frontend/src/api.ts` (`Workspace.virtual_nodes: VirtualNode[]`,
  new `VirtualNode` interface: `{id, label, kind: 'graphql_root' |
  'graphql_type'}`)
- Modify: `frontend/src/scene/layout.ts` (`computeLayout` needs to place
  virtual nodes too, since edges reference their ids — widen its input to
  accept a second `virtualNodes` list, or a unified `{id}`-shaped list
  fed into `forceSimulation` alongside real nodes; real vs. virtual stays
  distinguishable afterward by which input list an id came from)
- Modify: `frontend/src/scene/Graph.tsx` (render virtual nodes via a new
  component, never wire their click handler to `onSelect` — see below)
- Create: `frontend/src/scene/HubNode.tsx` (or a `isHub` prop on the
  existing `Node.tsx` — a real call to make during implementation, not
  fixed here; either way the visual must be *obviously* not a real,
  clickable endpoint)
- Test: extend `frontend/src/scene/layout.test.ts` for the merged-layout
  case; a new small test file for whatever pure logic ends up factored out
  (e.g. a `mergeForLayout` helper, if the implementation adds one)

**Visual identity decisions this task has to make for real** (not
prescribed here — SPEC.md §13's own precedent: exact visual constants get
decided once real content is in front of them, not guessed in the abstract):

- Hubs must read as structural landmarks, not endpoints: a different
  primitive shape than the sphere real nodes use (e.g. an icosahedron or
  torus), always the neutral `--mute`/`--hair` palette (never
  `--match`/`--violate` — a hub is never itself "verified" or "violated,"
  it has no drift status of its own; this is a real scope statement, not
  an oversight, and should be a one-line comment in the code, the same
  discipline `nodeSize.ts`'s own regression-guard comment used).
- Root hubs (`Query`/`Mutation`) should read as more prominent than type
  hubs, matching SPEC's own "roots" language — larger size and/or a
  distinct shape from ordinary type hubs, decided by eye once real
  countries.trevorblades.com content is on screen (same "decide against
  real content" discipline as the palette itself).
- **Hubs are not clickable** — no `onSelect` wiring, no detail panel. This
  project has no per-type detail to show (a hub only ever carries a label,
  never a schema, history, or send capability), so inventing a secondary
  panel just to have *something* happen on click would be exactly the kind
  of half-finished surface this codebase's own discipline avoids elsewhere
  (SPEC.md's "unverified, never a guess" ethos applied to UI, not just
  data). A label rendered directly in the 3D scene (e.g. `@react-three/drei`'s
  `Text`, already an available dependency via `@react-three/drei` — not a
  new one) is the honest alternative to a click affordance nothing backs.

- [ ] Land the interface/type changes.
- [ ] Extend `computeLayout` to lay out virtual nodes alongside real ones.
- [ ] Build the hub visual, wire non-clickable rendering into `Graph.tsx`.
- [ ] Unit tests for whatever pure logic exists outside the R3F components
      (component-level rendering itself stays covered by this project's
      existing live-browser-verification discipline, not a DOM-diffing
      unit test suite it has never used).

## Task 3: Live-tune the force layout for the new shape

**Files:** `frontend/src/scene/layout.ts` (the `forceManyBody`/`forceLink`
constants, currently tuned only for REST's shallower resource-tree shape)

High-degree root hubs (potentially dozens of fields fanning out from one
`Query` hub) are a real, different load on the existing force constants
(`charge().strength(-6)`, `link().distance(2.2)`) than REST's shallower
per-resource chains ever exercised. **This cannot be tuned correctly in the
abstract** — same reasoning SPEC.md §13 already gave for deferring the
original palette/force decision to Phase 0: it has to be tuned against real
rendered content. This task is: run the real `countries.trevorblades.com`
fixture (and, if available, one live schema with more root fields for a
harder case) in a real browser, and adjust constants until root hubs don't
overlap their own fanned-out fields and type hubs sit legibly among the
fields that point to them.

- [ ] Live-tune against `countries.trevorblades.com` in a real browser.
      Document the final constants and *why* in a code comment, the same
      way the original REST constants were never explained inline (a gap
      this task should not repeat).

## Verification discipline (same bar every phase in this repo holds itself to)

- Backend: real pytest coverage for `compute_graphql_edges`, using this
  project's own established GraphQL fixture shape, not invented toy schemas
  picked to make the algorithm look good.
- **Live-verify against a real, public GraphQL API** before calling this
  done — `https://countries.trevorblades.com/graphql` is this project's own
  precedent fixture (used in Phase 1b/1c/2b's own verifications). Confirm:
  real root hubs appear, real type hubs appear for object-returning fields
  and are absent for scalar-returning ones, fields visibly connect to both,
  clicking a real field node still opens the real request builder exactly
  as before (no regression), clicking a hub does nothing destructive.
- **REST regression check**: re-verify a Petstore workspace renders an
  identical graph to every prior phase's known result (`virtual_nodes: []`,
  same 19 nodes + 16 edges) — this task must not change REST's own edge
  computation or rendering path at all.

## Explicitly out of scope for this plan

- Any deeper GraphQL type graph (a type hub's own fields, nested object
  relationships two levels deep) — SPEC.md never asked for that; "fields
  fanning out to the types they return" is one hop, not a full schema
  crawl, and Phase 1b's own scope cut (no Node rows for non-root types)
  makes a deeper crawl a real, separate, much larger feature if ever
  wanted.
- `Subscription` fields — out of scope since Phase 1b, unchanged here.
- Any change to REST's own edge computation (`app/edges.py`) or visual
  identity — this plan only ever adds a new, parallel GraphQL path.
