"""MaxBodySizeMiddleware (2026-09-18 security-hardening plan): a real
oversized request must be rejected by declared Content-Length alone,
before the body is ever read -- verified two ways: a focused unit test
against the middleware class directly with a small cap (fast, precise
boundary), and an integration test against the real app confirming it
runs before auth even gets a chance to reject the request."""

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient as StarletteTestClient

from app.body_limit import MAX_BODY_BYTES, MaxBodySizeMiddleware
from fastapi.testclient import TestClient
from app.main import app as real_app


async def _echo(request):
    body = await request.body()
    return PlainTextResponse(str(len(body)))


def _make_test_app(max_bytes: int) -> Starlette:
    app = Starlette(routes=[Route("/echo", _echo, methods=["POST"])])
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=max_bytes)
    return app


def test_a_request_at_the_cap_is_allowed_through():
    client = StarletteTestClient(_make_test_app(max_bytes=10))
    r = client.post("/echo", content=b"x" * 10)
    assert r.status_code == 200
    assert r.text == "10"


def test_a_request_over_the_cap_is_rejected_with_413():
    client = StarletteTestClient(_make_test_app(max_bytes=10))
    r = client.post("/echo", content=b"x" * 11)
    assert r.status_code == 413


def test_a_request_with_no_content_length_is_not_blocked_by_this_check():
    # Stated honestly in body_limit.py's own docstring: this checks the
    # declared header, not a running byte count -- a request with no
    # Content-Length at all (e.g. chunked transfer-encoding) isn't caught
    # by this specific middleware. Confirmed here so the limitation is a
    # documented fact, not an assumption.
    client = StarletteTestClient(_make_test_app(max_bytes=10))
    r = client.post("/echo", content=iter([b"x" * 100]))
    assert r.status_code == 200


def test_the_real_app_rejects_an_oversized_request_before_auth_even_runs():
    client = TestClient(real_app)
    # No login performed -- if this reached the route it would 401, not
    # 413, so a 413 here proves the middleware runs outermost, ahead of
    # session/auth handling, exactly as intended.
    r = client.post(
        "/api/curl-parse",
        content=b"x" * (MAX_BODY_BYTES + 1),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 413
