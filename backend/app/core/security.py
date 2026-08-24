"""Security helpers: password hashing and verification.

Use argon2id (argon2-cffi) for new hashes. Keep compatibility with existing bcrypt
hashed passwords by detecting hash prefixes and delegating to passlib when needed.
"""
from typing import Optional

try:
    from passlib.hash import bcrypt
    _BCRYPT_AVAILABLE = True
except Exception:
    bcrypt = None
    _BCRYPT_AVAILABLE = False

import hashlib
import os
import base64

# Lightweight PBKDF2 fallback implementation to avoid external werkzeug dependency
def _pbkdf2_hash(password: str, iterations: int = 150000) -> str:
    salt = base64.urlsafe_b64encode(os.urandom(16)).decode('utf-8').rstrip('=')
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), iterations)
    hash_b64 = base64.urlsafe_b64encode(dk).decode('utf-8').rstrip('=')
    return f"pbkdf2:sha256:{iterations}${salt}${hash_b64}"

def _pbkdf2_verify(password: str, hashed: str) -> bool:
    try:
        parts = hashed.split('$')
        if not parts[0].startswith('pbkdf2:sha256'):
            return False
        iterations = int(parts[0].split(':')[-1])
        salt = parts[1]
        expected = parts[2]
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), iterations)
        got = base64.urlsafe_b64encode(dk).decode('utf-8').rstrip('=')
        return secrets_compare(got, expected)
    except Exception:
        return False


def secrets_compare(a: str, b: str) -> bool:
    # constant-time compare
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a.encode('utf-8'), b.encode('utf-8')):
        result |= x ^ y
    return result == 0

try:
    from argon2 import PasswordHasher
    _PH = PasswordHasher(time_cost=2, memory_cost=102400, parallelism=8, hash_len=32)
except Exception:
    _PH = None


def hash_password(password: str) -> str:
    """Hash password using argon2id when available, otherwise fall back to bcrypt.

    Returns the encoded hash string suitable for storage in DB.
    """
    if _PH is not None:
        return _PH.hash(password)
    if _BCRYPT_AVAILABLE and bcrypt is not None:
        return bcrypt.hash(password)
    # Last resort: use local PBKDF2 implementation
    return _pbkdf2_hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Verify a plaintext password against stored hash.

    Supports several hash formats: werkzeug pbkdf2 hashes (prefix 'pbkdf2:'),
    bcrypt ($2a$, $2b$, $2y$), and argon2 hashes produced by argon2.PasswordHasher.
    """
    if not hashed or not isinstance(hashed, str):
        return False
    lower = hashed.lower()
    try:
        # Werkzeug's generate_password_hash yields strings starting with algo:pbkdf2:sha256:...
        if lower.startswith("pbkdf2:") or lower.startswith("pbkdf2_sha256"):
            return _pbkdf2_verify(password, hashed)
        if lower.startswith("$2a$") or lower.startswith("$2b$") or lower.startswith("$2y$"):
            if _BCRYPT_AVAILABLE and bcrypt is not None:
                try:
                    return bcrypt.verify(password, hashed)
                except Exception:
                    return False
            # If bcrypt not available, fall through to werkzeug check
        if _PH is not None:
            try:
                # argon2 PasswordHasher expects (hash, secret) ordering in verify
                return _PH.verify(hashed, password)
            except Exception:
                # fall back to werkzeug/bcrypt attempts
                if _BCRYPT_AVAILABLE and bcrypt is not None:
                    try:
                        return bcrypt.verify(password, hashed)
                    except Exception:
                        return _pbkdf2_verify(password, hashed)
                return _pbkdf2_verify(password, hashed)
        # Last resort: try pbkdf2 and bcrypt
        try:
            if _pbkdf2_verify(password, hashed):
                return True
        except Exception:
            pass
        if _BCRYPT_AVAILABLE and bcrypt is not None:
            try:
                return bcrypt.verify(password, hashed)
            except Exception:
                return False
        return False
    except Exception:
        return False
