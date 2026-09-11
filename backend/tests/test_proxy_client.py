import socket

import httpx
import pytest
import respx

from app.proxy.client import ProxyError, fire_request


@respx.mock
def test_fire_request_returns_a_real_response_and_latency(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.get("https://93.184.216.34/pets/1").mock(return_value=httpx.Response(200, json={"id": 1, "name": "Fido"}))
    resp, latency_ms = fire_request("GET", "https://example.invalid/pets/1", None, None)
    assert resp.status_code == 200
    assert resp.json() == {"id": 1, "name": "Fido"}
    assert latency_ms >= 0


@respx.mock
def test_fire_request_sends_real_headers_and_body(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.post("https://93.184.216.34/pets").mock(return_value=httpx.Response(201))
    fire_request("POST", "https://example.invalid/pets", {"Content-Type": "application/json"}, '{"name":"Rex"}')
    sent = respx.calls.last.request
    assert sent.headers["content-type"] == "application/json"
    assert sent.content == b'{"name":"Rex"}'


def test_fire_request_rejects_an_unsafe_target():
    with pytest.raises(ProxyError):
        fire_request("GET", "http://127.0.0.1/secret", None, None)
