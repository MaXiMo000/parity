"""Fernet-encrypted at-rest storage for target-API credentials
(SPEC.md §7.4): defends against a database dump, not a full
secrets-manager setup -- stated plainly, not implied as more than it is.
Keyed by a server-held secret from the environment (FERNET_KEY),
generated once, never rotated casually (SPEC.md §12: a rotation
invalidates every already-stored credential -- there is no "re-encrypt
everything" migration path here, by design, matching the stated scope)."""

from __future__ import annotations

import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken


class CredentialDecryptionError(Exception):
    pass


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = os.environ["FERNET_KEY"]
    return Fernet(key.encode("utf-8"))


def encrypt_credential(value: str) -> bytes:
    return _fernet().encrypt(value.encode("utf-8"))


def decrypt_credential(token: bytes) -> str:
    try:
        return _fernet().decrypt(token).decode("utf-8")
    except InvalidToken as exc:
        raise CredentialDecryptionError(
            "stored credential could not be decrypted (wrong or rotated FERNET_KEY?)"
        ) from exc
