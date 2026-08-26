import logging
import os

logger = logging.getLogger(__name__)

#: Deployment environment. Only "production" is treated as strict: there, any
#: secret left at its insecure development default is a hard startup failure
#: rather than a silent fallback. Local dev and the test suite leave this unset
#: (or "development") and keep working with the documented dev defaults.
APP_ENV = os.environ.get("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV == "production"


class InsecureConfigurationError(RuntimeError):
    """Raised when a production deployment is missing a required secret.

    Failing at import/startup is deliberate: these values silently "work" when
    unset, so a warning alone would let a production deployment run with a
    publicly-known key (e.g. PII encrypted under a secret committed to the
    repository) with nothing to signal the problem.
    """


def require_secret(name: str, dev_default: str, *, hint: str = "") -> str:
    """Return the secret `name`, enforcing that production supplies a real one.

    In production the variable must be set, non-empty, and different from the
    development default. Anywhere else the dev default is used and a warning is
    logged, so local development and tests need no extra setup.
    """
    value = os.environ.get(name)
    if value is not None:
        value = value.strip()

    if IS_PRODUCTION:
        if not value:
            raise InsecureConfigurationError(
                f"{name} must be set when APP_ENV=production. {hint}".strip()
            )
        if value == dev_default:
            raise InsecureConfigurationError(
                f"{name} is still set to its insecure development default; "
                f"generate a real secret for production. {hint}".strip()
            )
        if value in PLACEHOLDER_VALUES:
            raise InsecureConfigurationError(
                f"{name} is still set to the placeholder from .env.example "
                f"({value!r}); generate a real secret for production. {hint}".strip()
            )
        return value

    if not value:
        logger.warning(
            "%s is not set; falling back to an insecure, publicly-known development "
            "default. This is NOT safe outside local development. %s",
            name,
            hint,
        )
        return dev_default
    return value


# Insecure development defaults. These are intentionally obvious: they are only
# ever reachable when APP_ENV is not "production" (see require_secret above).
DEV_SECRET_KEY = "dev-insecure-flask-secret-key-DO-NOT-USE-IN-PROD"
DEV_JWT_SECRET_KEY = "dev-insecure-jwt-secret-key-DO-NOT-USE-IN-PROD"
DEV_DATABASE_URL = "postgresql://postgres:password123@localhost:5433/mydb"

_GENERATE_HINT = "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""

#: Values that ship in `.env.example` as fill-me-in markers. They are not the
#: dev defaults, so without this set a deployment that copied `.env.example`
#: verbatim and flipped APP_ENV=production would sail past require_secret with
#: a secret whose value is published in this repository.
PLACEHOLDER_VALUES = frozenset({
    "replace-me-with-a-generated-secret",
    "replace-me",
    "change-me",
    "changeme",
    "your-secret-here",
    "TODO",
})


class Config:
    SECRET_KEY = require_secret("SECRET_KEY", DEV_SECRET_KEY, hint=_GENERATE_HINT)
    JWT_SECRET_KEY = require_secret("JWT_SECRET_KEY", DEV_JWT_SECRET_KEY, hint=_GENERATE_HINT)

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", DEV_DATABASE_URL)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_TOKEN_LOCATION = ["headers"]


def validate_required_secrets() -> None:
    """Resolve every production-required secret eagerly, at startup.

    `Config` only touches SECRET_KEY / JWT_SECRET_KEY. The two PII secrets are
    read lazily by `app.core.encrypted_type` on the first encrypt/decrypt, so a
    production deployment missing them used to boot cleanly and only blow up
    later, mid-request, as a 500. Calling this from `create_app()` turns that
    into the intended hard startup failure.

    Imported locally to avoid a circular import (encrypted_type imports config).
    """
    from app.core.encrypted_type import get_pii_secrets_for_validation

    get_pii_secrets_for_validation()
