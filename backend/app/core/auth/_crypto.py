"""Cryptographic primitives for the auth subsystem.

Pulled out of ``auth/__init__.py`` to keep the password-hashing,
token-hashing and base64url helpers in one focused module — they have
zero dependencies on the rest of the auth code and are independently
testable.

These are intentionally underscore-prefixed: they are internal helpers
re-exported by ``backend.app.core.auth`` for the legacy import path,
not part of the public auth API.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os


def _b64url_encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _b64url_decode(payload: str) -> bytes:
    padding = "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode((payload + padding).encode("ascii"))


def _hash_token(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _hash_password(password: str, iterations: int = 200_000) -> str:
    if not password:
        raise ValueError("password is required")
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = str(encoded or "").split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            str(password or "").encode("utf-8"),
            bytes.fromhex(salt),
            int(iterations),
        ).hex()
        return hmac.compare_digest(digest, expected)
    except Exception:
        return False
