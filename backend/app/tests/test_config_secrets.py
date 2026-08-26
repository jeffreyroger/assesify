"""Production must not silently fall back to insecure default secrets (spec §8).

These values all "work" when unset, so without an explicit guard a production
deployment can run with publicly-known keys — PII encrypted under a secret
committed to this repository, or JWTs signed with a forgeable one — and nothing
in the app's behavior would reveal it.
"""
import pytest

from app.core.config import (
    DEV_JWT_SECRET_KEY,
    DEV_SECRET_KEY,
    InsecureConfigurationError,
    require_secret,
)

DEV_DEFAULT = "dev-insecure-default"


def test_development_falls_back_to_dev_default(monkeypatch):
    """Local dev and the test suite must keep working with no extra setup."""
    monkeypatch.setattr("app.core.config.IS_PRODUCTION", False)
    monkeypatch.delenv("SOME_SECRET", raising=False)
    assert require_secret("SOME_SECRET", DEV_DEFAULT) == DEV_DEFAULT


def test_explicit_value_is_used_in_development(monkeypatch):
    monkeypatch.setattr("app.core.config.IS_PRODUCTION", False)
    monkeypatch.setenv("SOME_SECRET", "a-real-value")
    assert require_secret("SOME_SECRET", DEV_DEFAULT) == "a-real-value"


def test_production_rejects_unset_secret(monkeypatch):
    monkeypatch.setattr("app.core.config.IS_PRODUCTION", True)
    monkeypatch.delenv("SOME_SECRET", raising=False)
    with pytest.raises(InsecureConfigurationError, match="must be set"):
        require_secret("SOME_SECRET", DEV_DEFAULT)


def test_production_rejects_empty_secret(monkeypatch):
    """An empty/whitespace value is as insecure as an unset one."""
    monkeypatch.setattr("app.core.config.IS_PRODUCTION", True)
    monkeypatch.setenv("SOME_SECRET", "   ")
    with pytest.raises(InsecureConfigurationError, match="must be set"):
        require_secret("SOME_SECRET", DEV_DEFAULT)


def test_production_rejects_the_dev_default_value(monkeypatch):
    """Copying .env.example verbatim must not satisfy the check."""
    monkeypatch.setattr("app.core.config.IS_PRODUCTION", True)
    monkeypatch.setenv("SOME_SECRET", DEV_DEFAULT)
    with pytest.raises(InsecureConfigurationError, match="insecure development default"):
        require_secret("SOME_SECRET", DEV_DEFAULT)


def test_production_accepts_a_real_secret(monkeypatch):
    monkeypatch.setattr("app.core.config.IS_PRODUCTION", True)
    monkeypatch.setenv("SOME_SECRET", "a-genuinely-random-value")
    assert require_secret("SOME_SECRET", DEV_DEFAULT) == "a-genuinely-random-value"


@pytest.mark.parametrize("dev_default", [DEV_SECRET_KEY, DEV_JWT_SECRET_KEY])
def test_dev_defaults_are_self_evidently_not_production_values(dev_default):
    """The fallbacks are reachable only outside production; keep them obvious."""
    assert "DO-NOT-USE-IN-PROD" in dev_default


# ---------------------------------------------------------------------------
# Two gaps found while verifying the guard end-to-end (2026-08-26).
# ---------------------------------------------------------------------------

import re
from pathlib import Path

from app.core.config import PLACEHOLDER_VALUES

PRODUCTION_REQUIRED = [
    "SECRET_KEY",
    "JWT_SECRET_KEY",
    "PII_ENCRYPTION_KEY",
    "PII_LOOKUP_HASH_SECRET",
]


@pytest.mark.parametrize("placeholder", sorted(PLACEHOLDER_VALUES))
def test_production_rejects_env_example_placeholders(monkeypatch, placeholder):
    """Gap 1: `.env.example`'s fill-me-in markers are not the dev defaults.

    Without this, copying `.env.example` verbatim and setting APP_ENV=production
    passed the guard with a secret whose value is published in this repository.
    """
    monkeypatch.setattr("app.core.config.IS_PRODUCTION", True)
    monkeypatch.setenv("SOME_SECRET", placeholder)
    with pytest.raises(InsecureConfigurationError):
        require_secret("SOME_SECRET", DEV_DEFAULT)


def test_every_env_example_secret_placeholder_is_rejected():
    """Whatever `.env.example` ships as a value for a required secret must fail."""
    text = Path(__file__).resolve().parents[3].joinpath(".env.example").read_text(encoding="utf-8")
    for name in PRODUCTION_REQUIRED:
        match = re.search(rf"^{name}=(.*)$", text, re.MULTILINE)
        assert match, f"{name} is missing from .env.example"
        value = match.group(1).strip()
        assert value in PLACEHOLDER_VALUES, (
            f".env.example ships {name}={value!r}, which would pass the production "
            f"guard. Either make it a known placeholder or add it to PLACEHOLDER_VALUES."
        )


def test_env_example_contains_no_real_looking_secret():
    """No real secret may leak into the tracked template."""
    text = Path(__file__).resolve().parents[3].joinpath(".env.example").read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if any(tok in key.upper() for tok in ("SECRET", "KEY", "PASSWORD", "TOKEN")):
            value = value.strip()
            assert value == "" or value in PLACEHOLDER_VALUES or value.startswith("gemini-"), (
                f"{key} in .env.example has a non-placeholder value {value!r}"
            )


def test_pii_secrets_are_validated_at_startup_not_lazily(monkeypatch):
    """Gap 2: the PII secrets were read lazily, on first encrypt/decrypt.

    A production deployment missing them therefore booted cleanly and only
    failed later, mid-request, as a 500. `validate_required_secrets()` (called
    from `create_app`) forces them to resolve at startup instead.
    """
    from app.core import config as config_module

    monkeypatch.setattr(config_module, "IS_PRODUCTION", True)
    monkeypatch.delenv("PII_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("PII_LOOKUP_HASH_SECRET", raising=False)
    with pytest.raises(InsecureConfigurationError) as excinfo:
        config_module.validate_required_secrets()
    assert "PII_ENCRYPTION_KEY" in str(excinfo.value)


def test_validate_required_secrets_passes_in_development():
    """It must be a no-op for local dev and the test suite."""
    from app.core.config import validate_required_secrets

    validate_required_secrets()
