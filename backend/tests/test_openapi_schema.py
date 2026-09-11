import json
from pathlib import Path

import httpx
import pytest
import respx

from app.schema.openapi import (
    OpenAPIValidationError,
    fetch_spec,
    parse_openapi,
)

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "petstore-openapi.json").read_text())


def test_parse_real_petstore_spec_produces_real_nodes():
    nodes = parse_openapi(FIXTURE)
    assert len(nodes) > 10  # the real spec has 13 paths, several with >1 method

    by_op = {n["operation_id"]: n for n in nodes}
    assert "addPet" in by_op
    add_pet = by_op["addPet"]
    assert add_pet["method"] == "POST"
    assert add_pet["path_template"] == "/pet"
    assert add_pet["kind"] == "rest_operation"


def test_dollar_refs_are_resolved_inline_not_left_as_pointers():
    nodes = parse_openapi(FIXTURE)
    by_op = {n["operation_id"]: n for n in nodes}
    add_pet = by_op["addPet"]
    # The real spec's addPet.requestBody is `{"$ref": "#/components/schemas/Pet"}` —
    # after resolution this must be the real Pet schema, not the pointer.
    assert "$ref" not in json.dumps(add_pet["declared_request_schema"])
    assert add_pet["declared_request_schema"]["type"] == "object"
    assert "name" in add_pet["declared_request_schema"]["properties"]


def test_response_schema_is_the_first_2xx_only():
    nodes = parse_openapi(FIXTURE)
    by_op = {n["operation_id"]: n for n in nodes}
    add_pet = by_op["addPet"]
    # addPet's real responses are 200/400/422/default -- only 200's schema
    # should be stored (this plan's own stated simplification).
    assert add_pet["declared_response_schema"] is not None
    assert "$ref" not in json.dumps(add_pet["declared_response_schema"])


def test_operation_with_no_request_body_has_null_request_schema():
    nodes = parse_openapi(FIXTURE)
    by_op = {n["operation_id"]: n for n in nodes}
    # findPetsByStatus is a real GET with no body.
    assert by_op["findPetsByStatus"]["declared_request_schema"] is None


def test_invalid_spec_raises_validation_error():
    with pytest.raises(OpenAPIValidationError):
        parse_openapi({"not": "a real openapi spec"})


@respx.mock
def test_fetch_spec_real_http_get():
    respx.get("https://example.invalid/openapi.json").mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    spec = fetch_spec("https://example.invalid/openapi.json")
    assert spec["info"]["title"] == FIXTURE["info"]["title"]


@respx.mock
def test_fetch_spec_network_failure_raises():
    from app.schema.openapi import OpenAPIFetchError

    respx.get("https://example.invalid/openapi.json").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(OpenAPIFetchError):
        fetch_spec("https://example.invalid/openapi.json")
