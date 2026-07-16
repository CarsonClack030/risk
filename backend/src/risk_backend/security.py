"""Small security primitives shared by authentication and database migration."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets

PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 600_000
MAX_PASSWORD_ITERATIONS = 2_000_000
PASSWORD_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Return a salted PBKDF2 hash suitable for storing in SQLite."""
    salt = secrets.token_bytes(PASSWORD_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return "$".join(
        (
            PASSWORD_ALGORITHM,
            str(PASSWORD_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def is_password_hash(value: str) -> bool:
    """Identify hashes written by :func:`hash_password`."""
    return value.startswith(f"{PASSWORD_ALGORITHM}$")


def verify_password(password: str, stored_value: str) -> bool:
    """Verify a password while retaining compatibility with legacy plaintext rows."""
    if not is_password_hash(stored_value):
        return hmac.compare_digest(password, stored_value)

    try:
        algorithm, raw_iterations, raw_salt, raw_digest = stored_value.split("$", 3)
        iterations = int(raw_iterations)
        salt = base64.urlsafe_b64decode(raw_salt.encode("ascii"))
        expected = base64.urlsafe_b64decode(raw_digest.encode("ascii"))
    except (ValueError, TypeError, binascii.Error):
        return False
    if (
        algorithm != PASSWORD_ALGORITHM
        or iterations <= 0
        or iterations > MAX_PASSWORD_ITERATIONS
    ):
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)
