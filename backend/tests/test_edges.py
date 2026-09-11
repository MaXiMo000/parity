from app.edges import compute_rest_edges


def _node(id_, path):
    return {"id": id_, "path_template": path}


def test_nodes_sharing_a_resource_prefix_are_chained():
    nodes = [
        _node("a", "/pets"),
        _node("b", "/pets/{id}"),
        _node("c", "/pets/{id}/photos"),
    ]
    edges = compute_rest_edges(nodes)
    ids_in_edges = {i for pair in edges for i in pair}
    assert ids_in_edges == {"a", "b", "c"}
    assert len(edges) == 2  # a chain of 3 nodes has 2 edges


def test_nodes_in_different_resources_are_not_connected():
    nodes = [_node("a", "/pets"), _node("b", "/orders")]
    assert compute_rest_edges(nodes) == []


def test_real_petstore_shape_produces_a_real_multi_group_graph():
    # Mirrors the real fixture's actual top-level resources: pet, store, user.
    nodes = [
        _node("1", "/pet"), _node("2", "/pet/{petId}"), _node("3", "/pet/findByStatus"),
        _node("4", "/store/order"), _node("5", "/store/inventory"),
        _node("6", "/user"),
    ]
    edges = compute_rest_edges(nodes)
    connected = {i for pair in edges for i in pair}
    assert "6" not in connected  # /user is alone in its group -> no edges for it
    assert {"1", "2", "3"} & connected == {"1", "2", "3"}
    assert {"4", "5"} & connected == {"4", "5"}
