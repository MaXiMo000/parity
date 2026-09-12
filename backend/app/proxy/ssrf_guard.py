"""The real SSRF baseline guard (SPEC.md §7.3): DNS-resolve a target,
reject it if unsafe, and connect directly to the validated IP rather than
letting the HTTP client independently re-resolve at connect time (closing
the DNS-rebinding TOCTOU window Phase 1c's final review named). Shared by
every outbound fetch in this backend -- the two schema-fetch functions
(app/schema/openapi.py, app/schema/graphql.py) and the real
request-execution proxy (app/proxy/client.py, this plan's Task 4) -- so
there is exactly one copy of this security-critical logic. Moved here
from app/schema/openapi.py (Phase 1c's final review, finding M10: SPEC.md
§9 names this module explicitly; it lived in schema/openapi.py only
because no other caller existed yet)."""

from __future__ import annotations

import concurrent.futures
import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

# The full set of header names this backend treats as carrying real
# credentials -- the single source of truth (app/redact.py imports this
# same set rather than keeping its own, drifted copy; Phase 2a's final
# review found the two lists disagreed, letting X-Api-Key -- the
# dominant auth scheme for the REST APIs this tool targets, e.g. its own
# Petstore reference fixture -- leak to a redirect target unchanged).
SENSITIVE_HEADERS = {"authorization", "cookie", "proxy-authorization", "set-cookie", "x-api-key"}

_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=8)


def _resolve_safe_ip(hostname: str) -> str | None:
    """Resolves hostname and returns the first candidate IP to pin the
    real connection to, or None if resolution fails or ANY resolved
    address is unsafe -- a hostname that round-robins between a safe and
    an unsafe address must not pass on a lucky first answer. Rejects: not
    globally routable (subsumes private/loopback/link-local/reserved/
    CGNAT), multicast, a 6to4 address (2002::/16), and the NAT64
    well-known prefix 64:ff9b::/96 (maps to an internal IPv4 address on
    any NAT64 network -- exactly what an IPv6-only cloud subnet often
    is). Verified against the real ipaddress module, Phase 1c."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return None
    ips = [info[4][0] for info in infos]
    nat64 = ipaddress.ip_network("64:ff9b::/96")
    for raw in ips:
        addr = ipaddress.ip_address(raw)
        if not addr.is_global or addr.is_multicast or getattr(addr, "sixtofour", None) is not None or addr in nat64:
            return None
    return ips[0]


def _build_pinned_request(method: str, url: str, **kwargs: Any) -> httpx.Request | None:
    """Resolves and validates url's hostname via _resolve_safe_ip, then
    builds a real httpx.Request that connects directly to the validated
    IP -- closing the DNS-rebinding TOCTOU window between our own safety
    check and whatever httpx's own independent connection-time
    resolution would otherwise do. The original hostname/port is
    preserved as the Host header and the TLS SNI/certificate-hostname
    (extensions={"sni_hostname": ...}) so the request is indistinguishable
    from an ordinary one to the target server. Returns None if the URL
    isn't http(s), has no hostname (e.g. a relative redirect Location --
    rejected the same way a URL with no resolvable target always is), or
    the hostname doesn't resolve to an all-safe address set."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None
    hostname = parsed.hostname
    if not hostname:
        return None
    ip = _resolve_safe_ip(hostname)
    if ip is None:
        return None
    pinned_url = httpx.URL(url).copy_with(host=ip)
    headers = {**(kwargs.pop("headers", None) or {}), "Host": httpx.URL(url).netloc.decode("ascii")}
    return httpx.Request(method, pinned_url, headers=headers, extensions={"sni_hostname": hostname}, **kwargs)


def _send_with_wall_clock(req: httpx.Request, timeout: float) -> httpx.Response:
    """Sends req in a worker thread and enforces `timeout` as a genuine
    wall-clock bound via the thread's own result(timeout=...) -- httpx's
    per-operation timeout alone lets a slow-drip response reset its read
    timer on every chunk and run well past the configured limit (verified
    directly, Phase 2a's final review, finding I4: 20 one-second drips
    completed in ~20s against Client(timeout=15.0)). The abandoned thread
    on a real timeout is bounded by its own httpx timeout and the
    fixed-size pool -- it is not join()'d, but it cannot run forever."""
    def _do_send() -> httpx.Response:
        with httpx.Client(timeout=timeout) as client:
            return client.send(req, follow_redirects=False)

    future = _EXECUTOR.submit(_do_send)
    return future.result(timeout=timeout)


def send_pinned(
    method: str,
    url: str,
    error_cls: type[Exception],
    *,
    timeout: float = 15.0,
    extra_sensitive_headers: frozenset[str] = frozenset(),
    **kwargs: Any,
) -> httpx.Response:
    """Builds a pinned request (_build_pinned_request) and sends it,
    manually following at most one redirect hop -- the hop itself
    re-built and re-validated the same way, so an initially-safe URL that
    redirects to an internal address is still caught. Raises error_cls
    (each caller's own error type) on an unsafe/unresolvable target or a
    network failure at either hop.

    On a redirect whose target hostname differs from the original,
    strips Authorization/Cookie/Proxy-Authorization from any `headers`
    kwarg before re-sending -- the real fix for a trap Phase 1c's final
    review named and explicitly deferred (this function had no
    credential-carrying caller then; app/proxy/client.py, added in this
    plan, is the first one). A same-host redirect keeps every header
    unchanged, since a same-origin redirect has no reason to drop them.
    Callers may pass extra_sensitive_headers to strip additional,
    per-call header names (e.g. a workspace's custom credential header)
    beyond the fixed SENSITIVE_HEADERS set."""
    try:
        req = _build_pinned_request(method, url, **kwargs)
        if req is None:
            raise error_cls(f"{url} is not a permitted target")
        resp = _send_with_wall_clock(req, timeout)
    except error_cls:
        raise
    except concurrent.futures.TimeoutError:
        raise error_cls(f"{url} did not respond within {timeout}s")
    except Exception as exc:  # noqa: BLE001 -- _build_pinned_request can raise httpx.InvalidURL
        # (not an httpx.HTTPError subclass) on a malformed URL, and the
        # actual send can raise httpx.HTTPError on a network failure --
        # both are fetch-shaped failures from this function's caller's
        # point of view, so both become a clean error_cls instead of an
        # uncaught 500.
        raise error_cls(f"could not reach {url}: {exc}") from exc

    if resp.is_redirect:
        location = resp.headers.get("location")
        redirect_kwargs = dict(kwargs)
        if location:
            original_host = urlparse(url).hostname
            redirect_host = urlparse(location).hostname
            if redirect_host and redirect_host != original_host:
                headers = dict(redirect_kwargs.get("headers") or {})
                for key in list(headers):
                    if key.lower() in SENSITIVE_HEADERS | extra_sensitive_headers:
                        del headers[key]
                redirect_kwargs["headers"] = headers
                redirect_kwargs.pop("content", None)
                redirect_kwargs.pop("json", None)
        try:
            redirect_req = _build_pinned_request(method, location, **redirect_kwargs) if location else None
            if redirect_req is None:
                raise error_cls(f"{url} redirected to a target that is not permitted")
            resp = _send_with_wall_clock(redirect_req, timeout)
        except error_cls:
            raise
        except concurrent.futures.TimeoutError:
            raise error_cls(f"{location} did not respond within {timeout}s")
        except Exception as exc:  # noqa: BLE001 -- same reasoning as above
            raise error_cls(f"could not reach {location}: {exc}") from exc
    return resp
