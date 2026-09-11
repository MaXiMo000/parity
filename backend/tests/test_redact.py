from app.redact import redact_headers


def test_redacts_known_sensitive_headers_case_insensitively():
    result = redact_headers({"Authorization": "Bearer secret", "AUTHORIZATION": "x", "content-type": "application/json"})
    assert result["Authorization"] == "[REDACTED]"
    assert result["AUTHORIZATION"] == "[REDACTED]"
    assert result["content-type"] == "application/json"


def test_redacts_cookie_and_api_key_headers():
    result = redact_headers({"Cookie": "session=abc", "X-Api-Key": "k1", "Set-Cookie": "a=b"})
    assert result["Cookie"] == "[REDACTED]"
    assert result["X-Api-Key"] == "[REDACTED]"
    assert result["Set-Cookie"] == "[REDACTED]"


def test_leaves_unrelated_headers_untouched():
    result = redact_headers({"Accept": "application/json", "User-Agent": "test"})
    assert result == {"Accept": "application/json", "User-Agent": "test"}
