from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_curl_parse_route_returns_a_structured_request():
    r = client.post("/api/curl-parse", json={"curl": "curl -X POST 'https://api.example.com/x' -d 'a=1'"})
    assert r.status_code == 200
    body = r.json()
    assert body["method"] == "POST"
    assert body["url"] == "https://api.example.com/x"
    assert body["body"] == "a=1"


def test_curl_parse_route_rejects_invalid_input():
    r = client.post("/api/curl-parse", json={"curl": "not a curl command"})
    assert r.status_code == 422


def test_curl_parse_route_requires_the_curl_field():
    r = client.post("/api/curl-parse", json={})
    assert r.status_code == 422
