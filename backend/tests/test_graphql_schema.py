import json
import socket
from pathlib import Path

import httpx
import pytest
import respx

from app.schema.graphql import (
    GraphQLFetchError,
    GraphQLValidationError,
    fetch_introspection,
    parse_graphql,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "countries-graphql-introspection.json").read_text()
)

SDL = """
type Query {
  pet(id: ID!): Pet
  pets(limit: Int): [Pet!]!
}

type Mutation {
  addPet(name: String!): Pet
}

type Pet {
  id: ID!
  name: String!
  tag: String
}
"""


def test_parse_real_countries_introspection_produces_real_nodes():
    nodes = parse_graphql(FIXTURE["data"])
    assert len(nodes) == 6  # the real API has exactly 6 Query fields, no Mutation type
    by_field = {(n["type_name"], n["field_name"]): n for n in nodes}
    assert ("Query", "countries") in by_field
    countries = by_field[("Query", "countries")]
    assert countries["kind"] == "graphql_field"
    assert countries["method"] is None
    assert countries["declared_response_schema"] == {
        "kind": "LIST", "nullable": False,
        "of": {"kind": "NAMED", "name": "Country", "nullable": False},
    }


def test_parse_sdl_produces_query_and_mutation_nodes():
    nodes = parse_graphql(SDL)
    by_field = {(n["type_name"], n["field_name"]): n for n in nodes}
    assert set(by_field) == {("Query", "pet"), ("Query", "pets"), ("Mutation", "addPet")}

    pet = by_field[("Query", "pet")]
    assert pet["declared_request_schema"] == {"id": {"kind": "NAMED", "name": "ID", "nullable": False}}
    assert pet["declared_response_schema"] == {"kind": "NAMED", "name": "Pet", "nullable": True}

    pets = by_field[("Query", "pets")]
    assert pets["declared_request_schema"] == {"limit": {"kind": "NAMED", "name": "Int", "nullable": True}}
    assert pets["declared_response_schema"] == {
        "kind": "LIST", "nullable": False,
        "of": {"kind": "NAMED", "name": "Pet", "nullable": False},
    }

    add_pet = by_field[("Mutation", "addPet")]
    assert add_pet["declared_request_schema"] == {"name": {"kind": "NAMED", "name": "String", "nullable": False}}


def test_invalid_sdl_raises_validation_error():
    with pytest.raises(GraphQLValidationError):
        parse_graphql("type Query { pet(id ID!): Pet }")


def test_invalid_introspection_payload_raises_validation_error():
    with pytest.raises(GraphQLValidationError):
        parse_graphql({"not": "valid"})


@respx.mock
def test_fetch_introspection_real_http_post(monkeypatch):
    # "example.invalid" is RFC 2606 reserved and never actually resolves --
    # respx mocks the HTTP layer but not DNS, so fake a public-IP resolution
    # for our own pre-fetch safety check (app/schema/openapi.py's is_safe_url).
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.post("https://example.invalid/graphql").mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    data = fetch_introspection("https://example.invalid/graphql")
    assert data == FIXTURE["data"]


def test_fetch_introspection_rejects_a_private_ip_target():
    with pytest.raises(GraphQLFetchError):
        fetch_introspection("http://127.0.0.1:9999/graphql")


@respx.mock
def test_fetch_introspection_graphql_errors_raise(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.post("https://example.invalid/graphql").mock(
        return_value=httpx.Response(200, json={"errors": [{"message": "nope"}]})
    )
    with pytest.raises(GraphQLFetchError):
        fetch_introspection("https://example.invalid/graphql")


@respx.mock
def test_fetch_introspection_rejects_a_non_object_json_response(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.post("https://example.invalid/graphql").mock(
        return_value=httpx.Response(200, json=["not", "an", "object"])
    )
    with pytest.raises(GraphQLFetchError):
        fetch_introspection("https://example.invalid/graphql")
