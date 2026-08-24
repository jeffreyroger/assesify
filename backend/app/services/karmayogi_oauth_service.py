"""Karmayogi identity-link flows (spec §6.1).

`begin_authorization()` starts a PKCE authorization-code flow for a logged-in
Assesify user; `complete_authorization()` validates the returned `state`
(anti-CSRF, single-use, not expired, owned by the caller), exchanges the code
for tokens using the stored `code_verifier`, resolves the Karmayogi subject id
and persists it on `users.karmayogi_user_id`.

Everything here is transport-agnostic: the actual HTTP calls live in
`ml.integrations.karmayogi.oauth`, which is the seam tests mock.
"""
import os
from datetime import datetime

from app.models.users import db, User
from app.models.oauth_state import OAuthState, DEFAULT_TTL_SECONDS
from ml.integrations.karmayogi import oauth as ky_oauth
from ml.integrations.karmayogi.oauth import (
    OAuthError,
    OAuthConfigurationError,
)


def _config():
    return {
        "auth_url": os.getenv("KARMAYOGI_AUTH_URL", ""),
        "token_url": os.getenv("KARMAYOGI_TOKEN_URL", ""),
        "client_id": os.getenv("KARMAYOGI_CLIENT_ID", ""),
        "client_secret": os.getenv("KARMAYOGI_CLIENT_SECRET", ""),
        "redirect_uri": os.getenv("KARMAYOGI_REDIRECT_URI", ""),
        "scope": os.getenv("KARMAYOGI_SCOPE", ky_oauth.DEFAULT_SCOPE),
    }


def is_configured() -> bool:
    """True when enough config exists to run the PKCE flow."""
    cfg = _config()
    return bool(cfg["auth_url"] and cfg["token_url"] and cfg["client_id"])


def begin_authorization(user_id: int, redirect_uri: str | None = None, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> dict:
    """Create a PKCE challenge + state row and return the authorization URL.

    Raises `OAuthConfigurationError` when Karmayogi OAuth is not configured, so
    the caller can return a 503 rather than pretending the flow is available.
    """
    cfg = _config()
    redirect_uri = redirect_uri or cfg["redirect_uri"]
    missing = [k for k in ("auth_url", "token_url", "client_id") if not cfg[k]]
    if not redirect_uri:
        missing.append("redirect_uri")
    if missing:
        raise OAuthConfigurationError(
            "Karmayogi OAuth is not configured on this deployment.",
            details={"missing": missing},
        )

    verifier, challenge = ky_oauth.generate_pkce_pair()
    state = ky_oauth.generate_state()

    row = OAuthState(
        state=state,
        user_id=int(user_id),
        code_verifier=verifier,
        redirect_uri=redirect_uri,
        provider="karmayogi",
        expires_at=OAuthState.default_expiry(ttl_seconds),
    )
    db.session.add(row)
    db.session.commit()

    authorization_url = ky_oauth.build_authorize_url(
        client_id=cfg["client_id"],
        redirect_uri=redirect_uri,
        scope=cfg["scope"],
        state=state,
        code_challenge=challenge,
        auth_endpoint=cfg["auth_url"],
    )
    return {
        "authorization_url": authorization_url,
        "state": state,
        "code_challenge_method": "S256",
        "expires_at": row.expires_at.isoformat(),
    }


def complete_authorization(user_id: int, code: str, state: str) -> dict:
    """Validate `state`, exchange `code`, and persist the linked Karmayogi id.

    Raises `OAuthError` (subclass `OAuthConfigurationError`) on any failure;
    the state row is consumed on every accepted attempt so codes/states cannot
    be replayed.
    """
    if not code or not state:
        raise OAuthError("Both 'code' and 'state' are required.", code="VALIDATION_ERROR")

    row = OAuthState.query.filter_by(state=state, provider="karmayogi").first()
    # Unknown state, someone else's state, already-used state, or expired state
    # are all treated identically: a rejected (possibly forged) callback.
    if row is None or int(row.user_id) != int(user_id):
        raise OAuthError("Unrecognized or mismatched OAuth state.", code="INVALID_STATE")
    if row.consumed:
        raise OAuthError("This authorization request has already been used.", code="INVALID_STATE")
    if row.is_expired():
        raise OAuthError("This authorization request has expired; start the link again.", code="STATE_EXPIRED")

    # Single-use: burn the state before the network call so a concurrent replay
    # cannot ride the same verifier.
    row.consumed = True
    db.session.commit()

    cfg = _config()
    try:
        tokens = ky_oauth.exchange_code_for_token(
            token_url=cfg["token_url"],
            code=code,
            code_verifier=row.code_verifier,
            redirect_uri=row.redirect_uri,
            client_id=cfg["client_id"] or None,
            client_secret=cfg["client_secret"] or None,
        )
    except OAuthError:
        raise
    if not tokens:
        raise OAuthConfigurationError("Karmayogi token endpoint is not configured.")

    access_token = tokens.get("access_token")
    userinfo = ky_oauth.fetch_userinfo(access_token) if access_token else None
    karmayogi_user_id = ky_oauth.extract_user_id(tokens, userinfo)
    if not karmayogi_user_id:
        raise OAuthError(
            "Karmayogi did not return an identifiable user; identity not linked.",
            code="IDENTITY_UNRESOLVED",
        )

    user = User.query.get(int(user_id))
    if user is None:
        raise OAuthError("User not found.", code="NOT_FOUND")
    user.karmayogi_user_id = str(karmayogi_user_id)
    db.session.commit()

    return {
        "karmayogi_user_id": user.karmayogi_user_id,
        "linked_at": datetime.utcnow().isoformat(),
        "scope": tokens.get("scope"),
        "token_type": tokens.get("token_type"),
    }
