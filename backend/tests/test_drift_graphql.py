import json

from app.drift.graphql import check_graphql_drift

LIST_SCHEMA = {"kind": "LIST", "of": {"kind": "NAMED", "name": "Country", "nullable": False}, "nullable": False}
NAMED_NULLABLE_SCHEMA = {"kind": "NAMED", "name": "Country", "nullable": True}
INT_SCHEMA = {"kind": "NAMED", "name": "Int", "nullable": False}


def test_no_declared_schema_is_unverified_no_schema():
    status, detail = check_graphql_drift(None, json.dumps({"data": {"x": 1}}))
    assert status == "unverified_no_schema"


def test_matching_list_response_is_matched():
    body = json.dumps({"data": {"countries": [{"code": "US"}, {"code": "FR"}]}})
    status, detail = check_graphql_drift(LIST_SCHEMA, body)
    assert status == "matched"


def test_null_where_non_nullable_is_violated():
    body = json.dumps({"data": {"countries": None}})
    status, detail = check_graphql_drift(LIST_SCHEMA, body)
    assert status == "violated"
    assert "null is not allowed" in detail


def test_non_list_where_list_declared_is_violated():
    body = json.dumps({"data": {"countries": {"code": "US"}}})
    status, detail = check_graphql_drift(LIST_SCHEMA, body)
    assert status == "violated"
    assert "expected a list" in detail


def test_null_where_nullable_named_is_matched():
    body = json.dumps({"data": {"country": None}})
    status, detail = check_graphql_drift(NAMED_NULLABLE_SCHEMA, body)
    assert status == "matched"


def test_wrong_scalar_type_is_violated():
    body = json.dumps({"data": {"count": "not-an-int"}})
    status, detail = check_graphql_drift(INT_SCHEMA, body)
    assert status == "violated"
    assert "Int" in detail


def test_graphql_errors_in_the_response_are_violated():
    body = json.dumps({"errors": [{"message": "field not found"}], "data": None})
    status, detail = check_graphql_drift(INT_SCHEMA, body)
    assert status == "violated"
    assert "GraphQL errors" in detail


def test_non_json_body_is_violated():
    status, detail = check_graphql_drift(INT_SCHEMA, "not json")
    assert status == "violated"
    assert "not valid JSON" in detail


def test_custom_object_type_is_matched_without_deep_validation():
    # Country is a custom object type -- v1 only checks presence/nullability,
    # not Country's own fields (see this task's own stated scope boundary).
    body = json.dumps({"data": {"country": {"anything": "goes", "here": 123}}})
    status, detail = check_graphql_drift(NAMED_NULLABLE_SCHEMA, body)
    assert status == "matched"
