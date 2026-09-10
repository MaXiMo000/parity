from app.fixtures import FIXTURE_WORKSPACE_ID, fixture_edges, fixture_workspace


def test_fixture_workspace_shape():
    ws = fixture_workspace()
    assert ws["id"] == FIXTURE_WORKSPACE_ID
    assert ws["schema_kind"] == "openapi"
    assert len(ws["nodes"]) == 5

    by_op = {n["operation_id"]: n for n in ws["nodes"]}
    assert set(by_op) == {
        "list_tasks", "create_task", "get_task", "update_task", "delete_task",
    }
    assert by_op["list_tasks"]["method"] == "GET"
    assert by_op["list_tasks"]["path_template"] == "/tasks"
    assert by_op["get_task"]["path_template"] == "/tasks/{id}"
    # every node has both schema fields present (even if null), matching
    # SPEC.md §7.5's real column set — Phase 1 populates these for real,
    # Phase 0 must already carry the same keys.
    for n in ws["nodes"]:
        assert "declared_request_schema" in n
        assert "declared_response_schema" in n
        assert n["call_count"] == 0


def test_fixture_edges_only_reference_real_nodes():
    ws = fixture_workspace()
    node_ids = {n["id"] for n in ws["nodes"]}
    edges = fixture_edges()
    assert len(edges) == 3
    for a, b in edges:
        assert a in node_ids
        assert b in node_ids
