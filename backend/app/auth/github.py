"""Real GitHub OAuth (the standard authorization-code flow, SPEC.md
§7.4): builds the real authorize URL, exchanges a real code for a real
access token, and fetches the real authenticated user's GitHub profile.
These three calls all target GitHub's own fixed, well-known endpoints
(never a user-supplied URL), so they use plain httpx directly rather
than the SSRF-guarded send_pinned -- that guard exists for arbitrary
user-supplied target APIs (SPEC.md §7.3), not for calls this backend's
own code always sends to the same hardcoded host."""

from __future__ import annotations

import os
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


class GitHubOAuthError(Exception):
    pass


def new_state() -> str:
    return secrets.token_urlsafe(32)


def build_authorize_url(redirect_uri: str, state: str) -> str:
    params = {
        "client_id": os.environ["GITHUB_CLIENT_ID"],
        "redirect_uri": redirect_uri,
        "scope": "read:user",
        "state": state,
    }
    return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(code: str, redirect_uri: str) -> str:
    """Returns the real access token. Raises GitHubOAuthError on any
    failure (network, or GitHub itself rejecting the code)."""
    try:
        resp = httpx.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": os.environ["GITHUB_CLIENT_ID"],
                "client_secret": os.environ["GITHUB_CLIENT_SECRET"],
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise GitHubOAuthError(f"could not reach GitHub: {exc}") from exc
    if resp.status_code != 200:
        raise GitHubOAuthError(f"GitHub token exchange returned HTTP {resp.status_code}")
    payload = resp.json()
    token = payload.get("access_token")
    if not token:
        raise GitHubOAuthError(f"GitHub token exchange returned no access_token: {payload}")
    return token


def fetch_github_user(access_token: str) -> dict[str, Any]:
    """Returns the real {"id": int, "login": str, ...} profile. Raises
    GitHubOAuthError on any failure."""
    try:
        resp = httpx.get(
            GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise GitHubOAuthError(f"could not reach GitHub: {exc}") from exc
    if resp.status_code != 200:
        raise GitHubOAuthError(f"GitHub user lookup returned HTTP {resp.status_code}")
    return resp.json()
