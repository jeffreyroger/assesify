"""OAuth2 helpers for Karmayogi: PKCE flow and client-credentials flow (spec §6.1).

Two flows are supported:

* **client-credentials** — server-to-server token acquisition used by
  `KarmayogiClient` / `karmayogi_service` when calling the course catalog and
  progress-push APIs. `get_service_token()` caches the token in-process until
  shortly before it expires.
* **authorization-code + PKCE** — user-consented identity linking. The backend
  generates a `code_verifier`/`code_challenge` pair plus an anti-CSRF `state`,
  sends the user to the Karmayogi authorize endpoint, and later exchanges the
  returned `code` (bound to the stored verifier) for tokens.

Nothing here fabricates tokens: when the endpoints/credentials are not
configured the helpers raise `OAuthConfigurationError` or return ``None`` so the
caller can degrade gracefully (spec §6.4).
"""
import base64
import hashlib
import os
import secrets
import json
import logging
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

LOG = logging.getLogger(__name__)

DEFAULT_SCOPE = "openid profile"


class OAuthError(Exception):
    """Raised when a token endpoint responds with an error payload."""

    def __init__(self, message: str, code: str = "KARMAYOGI_OAUTH_ERROR", details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class OAuthConfigurationError(OAuthError):
    """Raised when required OAuth endpoints/credentials are not configured."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="KARMAYOGI_NOT_CONFIGURED", details=details)


# --------------------------------------------------------------------------- #
# PKCE primitives
# --------------------------------------------------------------------------- #

def generate_pkce_pair(length: int = 64):
    """Return (code_verifier, code_challenge) where challenge is base64url(SHA256(verifier))."""
    verifier = secrets.token_urlsafe(length)[:length]
    return verifier, derive_code_challenge(verifier)


def derive_code_challenge(verifier: str) -> str:
    """S256 challenge derivation: base64url(SHA256(verifier)) without padding."""
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def verify_code_challenge(verifier: str, challenge: str) -> bool:
    """Constant-time check that `challenge` is the S256 challenge for `verifier`."""
    return secrets.compare_digest(derive_code_challenge(verifier), challenge or "")


def generate_state(nbytes: int = 32) -> str:
    """Opaque, unguessable anti-CSRF state value."""
    return secrets.token_urlsafe(nbytes)


def build_authorize_url(
    client_id: str,
    redirect_uri: str,
    scope: str = "openid",
    state: str | None = None,
    code_challenge: str | None = None,
    auth_endpoint: str | None = None,
) -> str:
    base = auth_endpoint or os.getenv("KARMAYOGI_AUTH_URL")
    if not base:
        raise RuntimeError("Authorization endpoint not configured")
    params = {"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri, "scope": scope}
    if state:
        params["state"] = state
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"
    return f"{base}?{urlencode(params)}"


# --------------------------------------------------------------------------- #
# HTTP plumbing (single seam so tests can mock the token endpoint)
# --------------------------------------------------------------------------- #

def _post_form(url: str, body: dict, timeout: int = 5) -> dict:
    """POST an application/x-www-form-urlencoded body and return the JSON response.

    Raises `OAuthError` on transport failure, non-JSON bodies, or an OAuth
    `error` payload (RFC 6749 §5.2).
    """
    data = urlencode(body).encode("utf-8")
    req = Request(url, data=data, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:  # nosec B310 - configured endpoint
            raw = resp.read().decode("utf-8")
    except HTTPError as e:  # token endpoints return 400 with a JSON error body
        try:
            raw = e.read().decode("utf-8")
            payload = json.loads(raw)
        except Exception:
            raise OAuthError(f"Token endpoint returned HTTP {e.code}", details={"status": e.code})
        raise OAuthError(
            payload.get("error_description") or payload.get("error") or f"HTTP {e.code}",
            code="KARMAYOGI_OAUTH_ERROR",
            details={"oauth_error": payload.get("error"), "status": e.code},
        )
    except (URLError, TimeoutError, OSError) as e:
        raise OAuthError(f"Token endpoint unreachable: {e}", code="KARMAYOGI_UNAVAILABLE")
    try:
        payload = json.loads(raw)
    except Exception:
        raise OAuthError("Token endpoint returned a non-JSON response")
    if not isinstance(payload, dict):
        raise OAuthError("Token endpoint returned an unexpected payload shape")
    if payload.get("error"):
        raise OAuthError(
            payload.get("error_description") or payload["error"],
            details={"oauth_error": payload["error"]},
        )
    return payload


# --------------------------------------------------------------------------- #
# Authorization-code + PKCE
# --------------------------------------------------------------------------- #

def exchange_code_for_token(
    token_url: str,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> dict | None:
    """Exchange an authorization code (+ PKCE verifier) for tokens.

    Returns the token JSON, or ``None`` when `token_url` is falsy (kept for
    backwards compatibility with the previous signature). Raises `OAuthError`
    when the endpoint rejects the exchange or is unreachable.
    """
    if not token_url:
        LOG.debug("Token URL not configured; cannot exchange code")
        return None
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
    }
    if client_id:
        body["client_id"] = client_id
    if client_secret:
        body["client_secret"] = client_secret
    return _post_form(token_url, body)


def fetch_userinfo(access_token: str, userinfo_url: str | None = None, timeout: int = 5) -> dict | None:
    """Fetch the OIDC userinfo document for `access_token`.

    Returns ``None`` when no userinfo endpoint is configured or the call fails —
    the caller then falls back to identity claims present in the token response.
    """
    userinfo_url = userinfo_url or os.getenv("KARMAYOGI_USERINFO_URL")
    if not userinfo_url or not access_token:
        return None
    req = Request(userinfo_url, headers={
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    })
    try:
        with urlopen(req, timeout=timeout) as resp:  # nosec B310 - configured endpoint
            payload = json.loads(resp.read().decode("utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception as e:  # pragma: no cover - defensive
        LOG.debug("Karmayogi userinfo fetch failed: %s", e)
        return None


#: Claims Karmayogi/OIDC deployments use for the subject identifier, in priority order.
USER_ID_CLAIMS = ("karmayogi_user_id", "sub", "userId", "user_id", "identifier", "id")


def extract_user_id(*payloads: dict | None) -> str | None:
    """Pull the Karmayogi subject id out of a token/userinfo payload."""
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for claim in USER_ID_CLAIMS:
            value = payload.get(claim)
            if value:
                return str(value)
    return None


# --------------------------------------------------------------------------- #
# Client credentials (server-to-server)
# --------------------------------------------------------------------------- #

def client_credentials_token(
    token_url: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    scope: str | None = None,
) -> dict | None:
    """Obtain an access token via client_credentials. Returns token JSON or None.

    Does not create or store credentials; if required env vars are missing
    returns ``None``. Transport/endpoint errors are swallowed (``None``) so
    callers can fall back per spec §6.4.
    """
    token_url = token_url or os.getenv("KARMAYOGI_TOKEN_URL")
    client_id = client_id or os.getenv("KARMAYOGI_CLIENT_ID")
    client_secret = client_secret or os.getenv("KARMAYOGI_CLIENT_SECRET")
    if not token_url or not client_id or not client_secret:
        LOG.debug("Client credentials not configured")
        return None
    body = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}
    if scope:
        body["scope"] = scope
    try:
        return _post_form(token_url, body)
    except OAuthError as e:
        LOG.debug("Client credentials token fetch failed: %s", e)
        return None


# In-process cache for the service token: {"token": str, "expires_at": float}
_SERVICE_TOKEN_CACHE: dict = {}
#: Refresh this many seconds before the advertised expiry.
TOKEN_EXPIRY_SKEW = 30


def get_service_token(force_refresh: bool = False) -> str | None:
    """Return a cached client-credentials bearer token, refreshing when stale.

    Returns ``None`` when Karmayogi is not configured or the token endpoint is
    unreachable — callers must treat that as "no auth header" and degrade.
    """
    now = time.time()
    if not force_refresh:
        cached = _SERVICE_TOKEN_CACHE.get("token")
        if cached and _SERVICE_TOKEN_CACHE.get("expires_at", 0) > now:
            return cached
    payload = client_credentials_token()
    if not payload:
        _SERVICE_TOKEN_CACHE.clear()
        return None
    token = payload.get("access_token")
    if not token:
        _SERVICE_TOKEN_CACHE.clear()
        return None
    try:
        ttl = float(payload.get("expires_in", 3600))
    except (TypeError, ValueError):
        ttl = 3600.0
    _SERVICE_TOKEN_CACHE["token"] = token
    _SERVICE_TOKEN_CACHE["expires_at"] = now + max(ttl - TOKEN_EXPIRY_SKEW, 0)
    return token


def reset_service_token_cache():
    """Clear the cached service token (used by tests and on auth failures)."""
    _SERVICE_TOKEN_CACHE.clear()
