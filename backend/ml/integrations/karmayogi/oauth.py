"""OAuth helpers for Karmayogi: PKCE generator and client-credentials helper.

This module provides utilities to start a PKCE flow (generate code verifier/challenge
and authorization URL) and a client-credentials token fetch helper. The token
exchange functions will attempt network calls when URLs are configured; they do
not fabricate tokens when credentials are missing.
"""
import base64
import hashlib
import os
import secrets
import json
import logging
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError

LOG = logging.getLogger(__name__)


def generate_pkce_pair(length: int = 64):
    """Return (code_verifier, code_challenge) where challenge is base64url(SHA256(verifier))"""
    verifier = secrets.token_urlsafe(length)[:length]
    m = hashlib.sha256(verifier.encode("utf-8")).digest()
    challenge = base64.urlsafe_b64encode(m).decode("utf-8").rstrip("=")
    return verifier, challenge


def build_authorize_url(client_id: str, redirect_uri: str, scope: str = "openid", state: str | None = None, code_challenge: str | None = None, auth_endpoint: str | None = None) -> str:
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


def exchange_code_for_token(token_url: str, code: str, code_verifier: str, redirect_uri: str, client_id: str | None = None) -> dict | None:
    """Exchange an authorization code for tokens. Returns the JSON token response or None.

    This makes a POST to token_url with form-encoded parameters. If token_url is not set
    or the call fails, returns None (no fake tokens are produced).
    """
    if not token_url:
        LOG.debug("Token URL not configured; cannot exchange code")
        return None
    body = {"grant_type": "authorization_code", "code": code, "code_verifier": code_verifier, "redirect_uri": redirect_uri}
    if client_id:
        body["client_id"] = client_id
    data = urlencode(body).encode("utf-8")
    req = Request(token_url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except (URLError, Exception) as e:
        LOG.debug("Token exchange failed: %s", e)
        return None


def client_credentials_token(token_url: str | None = None, client_id: str | None = None, client_secret: str | None = None) -> dict | None:
    """Obtain an access token via client_credentials. Returns token JSON or None.

    Does not create or store credentials; if required env vars are missing returns None.
    """
    token_url = token_url or os.getenv("KARMAYOGI_TOKEN_URL")
    client_id = client_id or os.getenv("KARMAYOGI_CLIENT_ID")
    client_secret = client_secret or os.getenv("KARMAYOGI_CLIENT_SECRET")
    if not token_url or not client_id or not client_secret:
        LOG.debug("Client credentials not configured")
        return None
    body = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}
    data = urlencode(body).encode("utf-8")
    req = Request(token_url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except (URLError, Exception) as e:
        LOG.debug("Client credentials token fetch failed: %s", e)
        return None
