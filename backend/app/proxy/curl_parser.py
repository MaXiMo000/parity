"""Real curl-command parsing: a small hand-rolled parser over
shlex.split, covering exactly the flag set SPEC.md §7.1 names as needed
(-X/--request, -H/--header, -d/--data/--data-raw, -u/--user, -G,
-b/--cookie). `uncurl` (the existing library SPEC.md §7.1 said to try
first) was evaluated directly against real devtools-shaped curl commands
and found to genuinely conflate `-b` with `--data-binary` (real curl's
`-b` is `--cookie`; confirmed via uncurl's own argparse source: `-b` is
never mapped to cookies) and to have no `-G` support at all -- both flags
this project explicitly needs. Not used; this hand-rolled parser is the
real SPEC.md §13 decision, made against real data."""

from __future__ import annotations

import base64
import shlex
from typing import Any


class CurlParseError(Exception):
    pass


def _set_header(headers: dict[str, str], key: str, value: str) -> None:
    """Sets headers[key] = value, but reuses an existing key that matches
    case-insensitively -- real HTTP header names are case-insensitive, so
    a dict keyed by exact string would otherwise let e.g. a `-H
    'authorization: ...'` and a `-u user:pass`-derived `Authorization`
    header collide as two separate keys instead of one."""
    for existing in headers:
        if existing.lower() == key.lower():
            headers[existing] = value
            return
    headers[key] = value


def parse_curl(curl_command: str) -> dict[str, Any]:
    """Returns {"method": str, "url": str, "headers": dict[str, str],
    "body": str | None}. Anything outside the supported flag set is
    ignored, not rejected -- a real devtools-exported curl command
    carries many flags (--compressed, -s, --location) this tool has no
    use for, and the real content this portfolio's own testing
    discipline (SPEC.md §11) cares about is the ones it DOES support,
    verified against real devtools-shaped input."""
    try:
        tokens = shlex.split(curl_command)
    except ValueError as exc:
        raise CurlParseError(f"could not tokenize curl command: {exc}") from exc
    if not tokens or tokens[0] != "curl":
        raise CurlParseError("input must start with 'curl'")

    method: str | None = None
    url: str | None = None
    headers: dict[str, str] = {}
    data_parts: list[str] = []
    cookie_parts: list[str] = []
    user: str | None = None
    use_get_with_query = False

    i = 1
    while i < len(tokens):
        tok = tokens[i]
        if tok in ("-X", "--request"):
            i += 1
            method = tokens[i] if i < len(tokens) else None
        elif tok in ("-H", "--header"):
            i += 1
            if i < len(tokens):
                key, _, value = tokens[i].partition(":")
                _set_header(headers, key.strip(), value.strip())
        elif tok in ("-d", "--data", "--data-raw", "--data-binary"):
            i += 1
            if i < len(tokens):
                data_parts.append(tokens[i])
        elif tok in ("-u", "--user"):
            i += 1
            user = tokens[i] if i < len(tokens) else None
        elif tok == "-G":
            use_get_with_query = True
        elif tok in ("-b", "--cookie"):
            i += 1
            if i < len(tokens):
                cookie_parts.append(tokens[i])
        elif not tok.startswith("-") and url is None:
            url = tok
        i += 1

    if url is None:
        raise CurlParseError("no URL found in curl command")

    body = "&".join(data_parts) if data_parts else None
    if use_get_with_query and body:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{body}"
        body = None
        method = method or "GET"
    method = (method or ("POST" if body else "GET")).upper()

    if cookie_parts and not any(h.lower() == "cookie" for h in headers):
        headers["Cookie"] = "; ".join(cookie_parts)
    if user and not any(h.lower() == "authorization" for h in headers):
        headers["Authorization"] = "Basic " + base64.b64encode(user.encode()).decode()

    return {"method": method, "url": url, "headers": headers, "body": body}
