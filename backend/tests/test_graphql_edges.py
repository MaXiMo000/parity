from app.graphql_edges import compute_graphql_edges

NAMED = lambda name: {"kind": "NAMED", "name": name, "nullable": True}  # noqa: E731
LIST_OF = lambda inner: {"kind": "LIST", "of": inner, "nullable": True}  # noqa: E731


def test_two_fields_sharing_a_custom_object_return_type_get_a_shared_type_hub():
    nodes = [
        {"id": "pet", "type_name": "Query", "field_name": "pet", "declared_response_schema": NAMED("Pet")},
        {"id": "pets", "type_name": "Query", "field_name": "pets", "declared_response_schema": LIST_OF(NAMED("Pet"))},
    ]
    edges, virtual_nodes = compute_graphql_edges(nodes)
    type_hubs = [v for v in virtual_nodes if v["kind"] == "graphql_type"]
    assert type_hubs == [{"id": "type:Pet", "label": "Pet", "kind": "graphql_type"}]
    assert ("pet", "type:Pet") in edges
    assert ("pets", "type:Pet") in edges


def test_a_scalar_returning_field_gets_no_type_hub():
    nodes = [{"id": "count", "type_name": "Query", "field_name": "count", "declared_response_schema": NAMED("Int")}]
    edges, virtual_nodes = compute_graphql_edges(nodes)
    assert [v for v in virtual_nodes if v["kind"] == "graphql_type"] == []
    assert all(to != "type:Int" for _from, to in edges)


def test_every_field_gets_an_edge_to_its_own_root_hub():
    nodes = [
        {"id": "pet", "type_name": "Query", "field_name": "pet", "declared_response_schema": NAMED("Pet")},
        {"id": "addPet", "type_name": "Mutation", "field_name": "addPet", "declared_response_schema": NAMED("Pet")},
    ]
    edges, virtual_nodes = compute_graphql_edges(nodes)
    root_hubs = {v["id"]: v for v in virtual_nodes if v["kind"] == "graphql_root"}
    assert set(root_hubs) == {"root:Query", "root:Mutation"}
    assert ("root:Query", "pet") in edges
    assert ("root:Mutation", "addPet") in edges


def test_a_query_only_schema_produces_no_mutation_hub():
    nodes = [{"id": "pet", "type_name": "Query", "field_name": "pet", "declared_response_schema": NAMED("Pet")}]
    _edges, virtual_nodes = compute_graphql_edges(nodes)
    root_ids = {v["id"] for v in virtual_nodes if v["kind"] == "graphql_root"}
    assert root_ids == {"root:Query"}


def test_hub_ids_are_stable_across_repeated_calls_with_the_same_input():
    nodes = [
        {"id": "pet", "type_name": "Query", "field_name": "pet", "declared_response_schema": NAMED("Pet")},
        {"id": "pets", "type_name": "Query", "field_name": "pets", "declared_response_schema": LIST_OF(NAMED("Pet"))},
    ]
    edges_a, virtual_a = compute_graphql_edges(nodes)
    edges_b, virtual_b = compute_graphql_edges(nodes)
    assert edges_a == edges_b
    assert virtual_a == virtual_b


def test_a_field_with_no_declared_response_schema_still_gets_its_root_edge():
    nodes = [{"id": "mystery", "type_name": "Query", "field_name": "mystery", "declared_response_schema": None}]
    edges, virtual_nodes = compute_graphql_edges(nodes)
    assert ("root:Query", "mystery") in edges
    assert [v for v in virtual_nodes if v["kind"] == "graphql_type"] == []


def test_no_nodes_produces_no_edges_and_no_hubs():
    assert compute_graphql_edges([]) == ([], [])
