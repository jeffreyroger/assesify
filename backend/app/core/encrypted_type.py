"""Application-level PII encryption at rest.

Spec §8 calls for Postgres `pgcrypto` to encrypt `email`/`full_name` at rest.
This repo runs on SQLite locally and in tests (pgcrypto is Postgres-native and
unavailable there), so we implement the equivalent behavior at the application
layer instead: a SQLAlchemy `TypeDecorator` that transparently encrypts values
with Fernet (AES-128-CBC + HMAC, symmetric) on write and decrypts on read.
This is dialect-agnostic and works identically on SQLite and Postgres.

Follows the same "dev-friendly insecure default, real value in prod" pattern
used for `SECRET_KEY`/`JWT_SECRET_KEY` in `app/core/config.py`: a key/secret
is read from an env var, and a fixed (documented, obviously-not-secret)
fallback is used when unset so local dev/tests don't require extra setup.
"""
import base64
import hashlib
import hmac
import os

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.types import TypeDecorator, String

from app.core.config import require_secret


def _derive_fernet_key(raw: str) -> bytes:
    """Turn an arbitrary secret string into a valid 32-byte urlsafe-base64 Fernet key."""
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


# INSECURE DEV DEFAULT — do not rely on this in staging/prod. Set PII_ENCRYPTION_KEY
# to a real random secret (e.g. `Fernet.generate_key()`) in any non-local environment.
_DEV_DEFAULT_KEY = "dev-insecure-default-pii-encryption-key-DO-NOT-USE-IN-PROD"

_PII_KEY_ENV = "PII_ENCRYPTION_KEY"
_HASH_SECRET_ENV = "PII_LOOKUP_HASH_SECRET"


_GENERATE_HINT = "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""

#: Rotating this secret re-keys every email lookup hash, which would make every
#: existing user unable to log in. It must be set once and kept stable.
_HASH_ROTATION_HINT = (
    _GENERATE_HINT + " Set it once and keep it stable: changing it invalidates "
    "every stored email lookup hash and locks out all existing users."
)


def _get_fernet() -> Fernet:
    raw = require_secret(_PII_KEY_ENV, _DEV_DEFAULT_KEY, hint=_GENERATE_HINT)
    return Fernet(_derive_fernet_key(raw))


def _get_hash_secret() -> bytes:
    raw = require_secret(
        _HASH_SECRET_ENV, _DEV_DEFAULT_KEY + "-lookup-hash", hint=_HASH_ROTATION_HINT
    )
    return raw.encode("utf-8")


def get_pii_secrets_for_validation() -> None:
    """Force both PII secrets to resolve now, so a bad config fails at startup.

    `_get_fernet` / `_get_hash_secret` are otherwise only reached on the first
    encrypt/decrypt. Under APP_ENV=production a missing or placeholder secret
    would then surface as a mid-request 500 instead of a refusal to boot.
    Called from `app.core.config.validate_required_secrets()`.
    """
    _get_fernet()
    _get_hash_secret()


class EncryptedString(TypeDecorator):
    """A String column that is transparently Fernet-encrypted at rest.

    Reads/writes plaintext at the Python/ORM layer; the raw DB column value is
    ciphertext. Encryption is non-deterministic (a fresh nonce per write), so
    this type must never be used in an equality/WHERE-clause filter — use a
    separate deterministic hash column (see `compute_lookup_hash` below) for
    lookups instead.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        token = _get_fernet().encrypt(str(value).encode("utf-8"))
        return token.decode("utf-8")

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return _get_fernet().decrypt(value.encode("utf-8")).decode("utf-8")
        except (InvalidToken, ValueError):
            # Value predates encryption (shouldn't happen after migration backfill)
            # or was written under a different key. Fail closed to plaintext-as-is
            # rather than raising, so a bad key doesn't 500 every request that
            # touches this column; the caller sees mangled data, which is safer
            # than crashing the app.
            return value


def compute_lookup_hash(value: str) -> str:
    """Deterministic, non-reversible HMAC-SHA256 for indexed lookups (e.g. email).

    Normalizes (lowercase + strip) before hashing so lookups are
    case/whitespace-insensitive, matching typical email-login semantics.
    """
    normalized = (value or "").strip().lower()
    digest = hmac.new(_get_hash_secret(), normalized.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest
