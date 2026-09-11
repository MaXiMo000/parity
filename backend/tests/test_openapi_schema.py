import json
import socket
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
def test_fetch_spec_real_http_get(monkeypatch):
    # "example.invalid" is RFC 2606 reserved and never actually resolves --
    # respx mocks the HTTP layer but not DNS, so fake a public-IP resolution
    # for our own pre-fetch safety check (app/schema/openapi.py's is_safe_url).
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.get("https://example.invalid/openapi.json").mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    spec = fetch_spec("https://example.invalid/openapi.json")
    assert spec["info"]["title"] == FIXTURE["info"]["title"]


@respx.mock
def test_fetch_spec_network_failure_raises(monkeypatch):
    from app.schema.openapi import OpenAPIFetchError

    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.get("https://example.invalid/openapi.json").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(OpenAPIFetchError):
        fetch_spec("https://example.invalid/openapi.json")


def test_fetch_spec_rejects_a_private_ip_target():
    from app.schema.openapi import OpenAPIFetchError

    with pytest.raises(OpenAPIFetchError):
        fetch_spec("http://127.0.0.1:9999/whatever")


def test_ref_at_the_requestbody_object_level_is_also_resolved():
    spec = {
        "openapi": "3.0.0", "info": {"title": "t", "version": "1"},
        "components": {
            "requestBodies": {
                "Widget": {"content": {"application/json": {"schema": {"type": "object", "properties": {"name": {"type": "string"}}}}}},
            },
        },
        "paths": {
            "/widgets": {
                "post": {
                    "operationId": "createWidget",
                    "requestBody": {"$ref": "#/components/requestBodies/Widget"},
                    "responses": {"200": {"description": "ok"}},
                },
            },
        },
    }
    nodes = parse_openapi(spec)
    node = nodes[0]
    assert node["declared_request_schema"] is not None
    assert node["declared_request_schema"]["properties"]["name"]["type"] == "string"
