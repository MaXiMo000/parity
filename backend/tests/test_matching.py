from app.matching import match_rest_node

NODES = [
    {"id": "findByStatus", "method": "GET", "path_template": "/pet/findByStatus"},
    {"id": "findByTags", "method": "GET", "path_template": "/pet/findByTags"},
    {"id": "getPetById", "method": "GET", "path_template": "/pet/{petId}"},
    {"id": "addPet", "method": "POST", "path_template": "/pet"},
]


def test_literal_segment_beats_a_template_at_the_same_position():
    result = match_rest_node(NODES, "GET", "https://api.example.com/api/v3/pet/findByStatus", "/api/v3")
    assert result["id"] == "findByStatus"


def test_a_real_id_matches_the_template_node():
    result = match_rest_node(NODES, "GET", "https://api.example.com/api/v3/pet/123", "/api/v3")
    assert result["id"] == "getPetById"


def test_matches_by_method_too_not_only_path():
    result = match_rest_node(NODES, "POST", "https://api.example.com/api/v3/pet", "/api/v3")
    assert result["id"] == "addPet"


def test_no_match_on_segment_count_mismatch():
    assert match_rest_node(NODES, "GET", "https://api.example.com/api/v3/pet/1/extra", "/api/v3") is None


def test_no_match_when_no_node_has_that_method():
    assert match_rest_node(NODES, "DELETE", "https://api.example.com/api/v3/pet/1", "/api/v3") is None


def test_empty_base_path_still_matches_a_request_with_no_prefix():
    nodes = [{"id": "root", "method": "GET", "path_template": "/pets"}]
    result = match_rest_node(nodes, "GET", "https://api.example.com/pets", "")
    assert result["id"] == "root"


from app.matching import match_graphql_node

GRAPHQL_NODES = [
    {"id": "queryPet", "type_name": "Query", "field_name": "pet"},
    {"id": "queryPets", "type_name": "Query", "field_name": "pets"},
    {"id": "mutationAddPet", "type_name": "Mutation", "field_name": "addPet"},
]


def test_matches_a_real_query_by_operation_and_field():
    import json
    body = json.dumps({"query": "{ pet(id: 1) { name } }"})
    result = match_graphql_node(GRAPHQL_NODES, body)
    assert result["id"] == "queryPet"


def test_matches_an_explicit_mutation():
    import json
    body = json.dumps({"query": "mutation { addPet(name: \"Rex\") { id } }"})
    result = match_graphql_node(GRAPHQL_NODES, body)
    assert result["id"] == "mutationAddPet"


def test_no_match_when_the_field_is_unknown():
    import json
    body = json.dumps({"query": "{ totallyUnknownField }"})
    assert match_graphql_node(GRAPHQL_NODES, body) is None


def test_no_match_on_malformed_graphql():
    import json
    body = json.dumps({"query": "not valid graphql {{{"})
    assert match_graphql_node(GRAPHQL_NODES, body) is None


def test_no_match_when_body_is_not_json():
    assert match_graphql_node(GRAPHQL_NODES, "not json at all") is None


def test_no_match_when_body_has_no_query_field():
    import json
    assert match_graphql_node(GRAPHQL_NODES, json.dumps({"notQuery": "x"})) is None


def test_no_match_when_body_is_empty():
    assert match_graphql_node(GRAPHQL_NODES, None) is None
    assert match_graphql_node(GRAPHQL_NODES, "") is None
