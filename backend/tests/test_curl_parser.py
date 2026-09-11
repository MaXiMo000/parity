import pytest

from app.proxy.curl_parser import CurlParseError, parse_curl

# Shaped exactly like a real Chrome DevTools "Copy as cURL (bash)" export
# for a POST with a bearer token and a JSON body (SPEC.md §11: tested
# against a real devtools shape, not a hand-typed minimal example).
DEVTOOLS_POST = """curl 'https://api.example.com/v1/pets' \\
  -H 'authority: api.example.com' \\
  -H 'accept: application/json' \\
  -H 'authorization: Bearer abc123' \\
  -H 'content-type: application/json' \\
  -H 'user-agent: Mozilla/5.0' \\
  --data-raw '{"name":"Fido","tag":"dog"}' """


def test_parses_a_real_devtools_post_with_bearer_token_and_json_body():
    result = parse_curl(DEVTOOLS_POST)
    assert result["method"] == "POST"
    assert result["url"] == "https://api.example.com/v1/pets"
    assert result["headers"]["authorization"] == "Bearer abc123"
    assert result["headers"]["content-type"] == "application/json"
    assert result["body"] == '{"name":"Fido","tag":"dog"}'


def test_parses_a_get_with_query_params_and_no_explicit_method():
    result = parse_curl("curl 'https://api.example.com/v1/pets?limit=10&tag=dog' -H 'accept: application/json'")
    assert result["method"] == "GET"
    assert result["url"] == "https://api.example.com/v1/pets?limit=10&tag=dog"


def test_parses_explicit_put_with_cookie_and_data():
    result = parse_curl("curl -X PUT 'https://api.example.com/v1/pets/1' -b 'session=xyz' -d 'name=Rex'")
    assert result["method"] == "PUT"
    assert result["headers"]["Cookie"] == "session=xyz"
    assert result["body"] == "name=Rex"


def test_parses_basic_auth_into_an_authorization_header():
    result = parse_curl("curl -u user:pass 'https://api.example.com/v1/secure'")
    assert result["headers"]["Authorization"] == "Basic dXNlcjpwYXNz"


def test_parses_g_flag_as_query_params_not_a_body():
    result = parse_curl("curl -G 'https://api.example.com/v1/search' -d 'q=fido' -d 'limit=5'")
    assert result["method"] == "GET"
    assert result["url"] == "https://api.example.com/v1/search?q=fido&limit=5"
    assert result["body"] is None


def test_rejects_input_that_does_not_start_with_curl():
    with pytest.raises(CurlParseError):
        parse_curl("not a curl command")


def test_rejects_a_command_with_no_url():
    with pytest.raises(CurlParseError):
        parse_curl("curl -X GET")


def test_a_header_and_a_derived_auth_header_do_not_collide_by_case():
    result = parse_curl("curl -u user:pass -H 'authorization: Bearer abc' 'https://api.example.com/x'")
    assert result["headers"] == {"authorization": "Bearer abc"}


def test_a_header_and_a_derived_cookie_header_do_not_collide_by_case():
    result = parse_curl("curl -b 'session=xyz' -H 'cookie: existing=1' 'https://api.example.com/x'")
    assert result["headers"] == {"cookie": "existing=1"}
