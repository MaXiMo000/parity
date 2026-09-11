from app.drift.rest import check_rest_drift

SCHEMA = {
    "type": "object",
    "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
    "required": ["id", "name"],
}


def test_no_declared_schema_is_unverified_no_schema():
    status, detail = check_rest_drift(None, '{"id": 1, "name": "Fido"}')
    assert status == "unverified_no_schema"
    assert detail is None


def test_matching_response_is_matched():
    status, detail = check_rest_drift(SCHEMA, '{"id": 1, "name": "Fido"}')
    assert status == "matched"
    assert detail is None


def test_wrong_type_is_violated_with_a_real_diff():
    status, detail = check_rest_drift(SCHEMA, '{"id": "not-an-int", "name": "Fido"}')
    assert status == "violated"
    assert "id" in detail
    assert "integer" in detail


def test_missing_required_field_is_violated():
    status, detail = check_rest_drift(SCHEMA, '{"id": 1}')
    assert status == "violated"
    assert "name" in detail


def test_non_json_body_is_violated():
    status, detail = check_rest_drift(SCHEMA, "not json at all")
    assert status == "violated"
    assert "not valid JSON" in detail
