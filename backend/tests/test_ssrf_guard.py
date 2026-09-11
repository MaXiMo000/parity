"""The adversarial pass SPEC.md §11 requires once Phase 2's real
request-firing exists: prove the SSRF boundary actually holds, not just
that it's present. Also covers the redirect-credential-stripping
behavior added in this plan (Task 1)."""

import socket

import httpx
import pytest
import respx

from app.proxy.ssrf_guard import _resolve_safe_ip, send_pinned


class _FetchError(Exception):
    pass


def test_resolve_safe_ip_rejects_nat64_and_sixtofour_addresses():
    assert _resolve_safe_ip("64:ff9b::a00:1") is None  # NAT64, maps to 10.0.0.1
    assert _resolve_safe_ip("2002:7f00:1::") is None    # 6to4, maps to 127.0.0.1


def test_send_pinned_rejects_loopback():
    with pytest.raises(_FetchError):
        send_pinned("GET", "http://127.0.0.1/secret", _FetchError)


def test_send_pinned_rejects_the_cloud_metadata_endpoint():
    with pytest.raises(_FetchError):
        send_pinned("GET", "http://169.254.169.254/latest/meta-data/", _FetchError)


def test_send_pinned_rejects_an_rfc1918_private_address():
    with pytest.raises(_FetchError):
        send_pinned("GET", "http://10.0.0.5/internal", _FetchError)


def test_send_pinned_rejects_explicit_localhost_by_hostname():
    with pytest.raises(_FetchError):
        send_pinned("GET", "http://localhost/", _FetchError)


@respx.mock
def test_send_pinned_strips_credentials_on_a_cross_host_redirect(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.get("https://93.184.216.34/old").mock(
        return_value=httpx.Response(302, headers={"location": "https://other.invalid/new"})
    )
    respx.get("https://93.184.216.34/new").mock(return_value=httpx.Response(200))
    send_pinned("GET", "https://example.invalid/old", _FetchError, headers={"Authorization": "Bearer secret"})
    sent_headers = respx.calls.last.request.headers
    assert "authorization" not in sent_headers


@respx.mock
def test_send_pinned_preserves_credentials_on_a_same_host_redirect(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.get("https://93.184.216.34/old").mock(
        return_value=httpx.Response(302, headers={"location": "https://example.invalid/new"})
    )
    respx.get("https://93.184.216.34/new").mock(return_value=httpx.Response(200))
    send_pinned("GET", "https://example.invalid/old", _FetchError, headers={"Authorization": "Bearer secret"})
    sent_headers = respx.calls.last.request.headers
    assert sent_headers.get("authorization") == "Bearer secret"


@respx.mock
def test_send_pinned_strips_x_api_key_on_a_cross_host_redirect(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.get("https://93.184.216.34/old").mock(
        return_value=httpx.Response(302, headers={"location": "https://other.invalid/new"})
    )
    respx.get("https://93.184.216.34/new").mock(return_value=httpx.Response(200))
    send_pinned("GET", "https://example.invalid/old", _FetchError, headers={"X-Api-Key": "supersecret"})
    sent_headers = respx.calls.last.request.headers
    assert "x-api-key" not in sent_headers


@respx.mock
def test_send_pinned_strips_the_body_on_a_cross_host_redirect(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    respx.post("https://93.184.216.34/old").mock(
        return_value=httpx.Response(302, headers={"location": "https://other.invalid/new"})
    )
    respx.post("https://93.184.216.34/new").mock(return_value=httpx.Response(200))
    send_pinned("POST", "https://example.invalid/old", _FetchError, content=b"sensitive-body-data")
    sent_content = respx.calls.last.request.content
    assert sent_content == b""


@respx.mock
def test_send_pinned_enforces_a_genuine_wall_clock_timeout(monkeypatch):
    import time

    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )

    def slow_side_effect(request):
        time.sleep(2)
        return httpx.Response(200)

    respx.get("https://93.184.216.34/slow").mock(side_effect=slow_side_effect)
    start = time.monotonic()
    with pytest.raises(_FetchError):
        send_pinned("GET", "https://example.invalid/slow", _FetchError, timeout=0.5)
    elapsed = time.monotonic() - start
    assert elapsed < 1.5  # well under the 2s the mock sleeps -- proves the wall clock, not the mock's own delay, bounded this
