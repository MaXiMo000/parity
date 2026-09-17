"""Pydantic request models (2026-09-18 security-hardening plan, Task 3):
replaces every route's raw `body: dict` with a real, validated schema --
malformed input is rejected by FastAPI's own validation before a route
handler ever runs, instead of each route manually calling dict.get() and
checking by hand. Every check here is a deliberate match for the manual
check it replaces, not a behavior change (verified against this suite:
no test asserts exact 422 error body content, only status codes -- a
Pydantic validation error's body shape differs from a plain
HTTPException's, but the status code and the actual accept/reject
decision are identical)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class CreateWorkspaceRequest(BaseModel):
    name: str
    schema_kind: Literal["openapi", "graphql"]
    schema_source_url: str | None = None
    raw_schema: Any = None

    @model_validator(mode="after")
    def _check(self) -> "CreateWorkspaceRequest":
        if not self.name:
            raise ValueError("name is required")
        # Matches the original dict/str truthiness exactly: an empty dict
        # or empty string raw_schema counts as "not provided", the same
        # as the manual bool(raw) check it replaces.
        if bool(self.schema_source_url) == bool(self.raw_schema):
            raise ValueError("exactly one of schema_source_url or raw_schema is required")
        return self


class SetCredentialRequest(BaseModel):
    header_name: str
    value: str

    @model_validator(mode="after")
    def _check(self) -> "SetCredentialRequest":
        if not self.header_name or not self.value:
            raise ValueError("header_name and value are required")
        return self


class SendRequestRequest(BaseModel):
    method: str
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "SendRequestRequest":
        if not self.method or not self.url:
            raise ValueError("method and url are required")
        return self


class CurlParseRequest(BaseModel):
    curl: str

    @model_validator(mode="after")
    def _check(self) -> "CurlParseRequest":
        if not self.curl.strip():
            raise ValueError("curl is required")
        return self
