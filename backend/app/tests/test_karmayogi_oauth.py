"""Karmayogi OAuth2 flows (spec §6.1) — PKCE link + client-credentials.

All HTTP is mocked at `ml.integrations.karmayogi.oauth._post_form` /
`fetch_userinfo`; no live Karmayogi endpoint is contacted.
"""
import os

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('JWT_SECRET_KEY', 'test-jwt-secret')

from app.main import create_app
from app.models.oauth_state import OAuthState
from app.models.users import db, User
from flask_jwt_extended import create_access_token
from ml.integrations.karmayogi import oauth as ky_oauth
from ml.integrations.karmayogi.oauth import (
    OAuthError,
    derive_code_challenge,
    generate_pkce_pair,
    verify_code_challenge,
)

AUTH_URL = "https://karmayogi.test/auth/realms/sunbird/protocol/openid-connect/auth"
TOKEN_URL = "https://karmayogi.test/auth/realms/sunbird/protocol/openid-connect/token"


@pytest.fixture
def oauth_env(monkeypatch):
    monkeypatch.setenv("KARMAYOGI_AUTH_URL", AUTH_URL)
    monkeypatch.setenv("KARMAYOGI_TOKEN_URL", TOKEN_URL)
    monkeypatch.setenv("KARMAYOGI_CLIENT_ID", "assesify-test-client")
    monkeypatch.setenv("KARMAYOGI_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("KARMAYOGI_REDIRECT_URI", "https://assesify.test/karmayogi/callback")
    ky_oauth.reset_service_token_cache()
    yield
    ky_oauth.reset_service_token_cache()


@pytest.fixture
def app():
    app = create_app()
    with app.app_context():
        db.create_all()
    yield app


def _make_users(app):
    with app.app_context():
        a = User(email='ky-a@example.com', full_name='KY A', password_hash='fakehash')
        b = User(email='ky-b@example.com', full_name='KY B', password_hash='fakehash')
        db.session.add_all([a, b])
        db.session.commit()
        return a.id, create_access_token(identity=str(a.id)), b.id, create_access_token(identity=str(b.id))


# --------------------------------------------------------------------------- #
# PKCE primitives
# --------------------------------------------------------------------------- #

def test_pkce_challenge_derivation_is_s256_and_verifiable():
    verifier, challenge = generate_pkce_pair(64)
    # base64url, unpadded
    assert "=" not in challenge and "+" not in challenge and "/" not in challenge
    assert challenge == derive_code_challenge(verifier)
    assert verify_code_challenge(verifier, challenge) is True
    assert verify_code_challenge(verifier, challenge[:-1] + "x") is False
    # Distinct verifiers each time
    assert generate_pkce_pair()[0] != generate_pkce_pair()[0]


# --------------------------------------------------------------------------- #
# /auth/karmayogi/authorize
# --------------------------------------------------------------------------- #

def test_authorize_returns_url_with_state_and_s256_challenge(app, oauth_env):
    client = app.test_client()
    user_id, token, _, _ = _make_users(app)

    resp = client.post('/api/v1/auth/karmayogi/authorize', json={},
                       headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['authorization_url'].startswith(AUTH_URL)
    assert 'code_challenge=' in body['authorization_url']
    assert 'code_challenge_method=S256' in body['authorization_url']
    assert f"state={body['state']}" in body['authorization_url']

    with app.app_context():
        row = OAuthState.query.filter_by(state=body['state']).one()
        assert row.user_id == user_id
        assert row.consumed is False
        # The verifier stays server-side and matches the challenge that went out.
        assert f"code_challenge={derive_code_challenge(row.code_verifier)}" in body['authorization_url']


def test_authorize_requires_auth(app, oauth_env):
    assert app.test_client().post('/api/v1/auth/karmayogi/authorize', json={}).status_code == 401


def test_authorize_returns_503_when_not_configured(app, monkeypatch):
    for var in ("KARMAYOGI_AUTH_URL", "KARMAYOGI_TOKEN_URL", "KARMAYOGI_CLIENT_ID", "KARMAYOGI_REDIRECT_URI"):
        monkeypatch.delenv(var, raising=False)
    client = app.test_client()
    _, token, _, _ = _make_users(app)
    resp = client.post('/api/v1/auth/karmayogi/authorize', json={},
                       headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 503
    err = resp.get_json()['error']
    assert err['code'] == 'KARMAYOGI_NOT_CONFIGURED'
    assert 'auth_url' in err['details']['missing']


# --------------------------------------------------------------------------- #
# /auth/karmayogi/callback
# --------------------------------------------------------------------------- #

def _start_flow(client, token):
    resp = client.post('/api/v1/auth/karmayogi/authorize', json={},
                       headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    return resp.get_json()['state']


def test_callback_exchanges_code_and_links_identity(app, oauth_env, monkeypatch):
    client = app.test_client()
    user_id, token, _, _ = _make_users(app)
    state = _start_flow(client, token)

    captured = {}

    def fake_post_form(url, body, timeout=5):
        captured['url'] = url
        captured['body'] = body
        return {"access_token": "ky-access", "token_type": "Bearer", "expires_in": 3600, "scope": "openid profile"}

    monkeypatch.setattr(ky_oauth, "_post_form", fake_post_form)
    monkeypatch.setattr(ky_oauth, "fetch_userinfo", lambda t, *a, **k: {"sub": "ky-user-42", "name": "KY A"})

    resp = client.post('/api/v1/auth/karmayogi/callback',
                       json={"code": "auth-code-abc", "state": state},
                       headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()['karmayogi_user_id'] == 'ky-user-42'

    # The token exchange carried the PKCE verifier matching the issued challenge.
    assert captured['url'] == TOKEN_URL
    assert captured['body']['grant_type'] == 'authorization_code'
    assert captured['body']['code'] == 'auth-code-abc'
    with app.app_context():
        row = OAuthState.query.filter_by(state=state).one()
        assert row.consumed is True
        assert captured['body']['code_verifier'] == row.code_verifier
        assert User.query.get(user_id).karmayogi_user_id == 'ky-user-42'


def test_callback_falls_back_to_token_claims_when_no_userinfo(app, oauth_env, monkeypatch):
    client = app.test_client()
    user_id, token, _, _ = _make_users(app)
    state = _start_flow(client, token)

    monkeypatch.setattr(ky_oauth, "_post_form",
                        lambda url, body, timeout=5: {"access_token": "t", "userId": "ky-99"})
    monkeypatch.setattr(ky_oauth, "fetch_userinfo", lambda *a, **k: None)

    resp = client.post('/api/v1/auth/karmayogi/callback',
                       json={"code": "c", "state": state},
                       headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    assert resp.get_json()['karmayogi_user_id'] == 'ky-99'
    with app.app_context():
        assert User.query.get(user_id).karmayogi_user_id == 'ky-99'


def test_callback_rejects_forged_state_csrf(app, oauth_env, monkeypatch):
    client = app.test_client()
    _, token, _, _ = _make_users(app)
    _start_flow(client, token)

    called = {"n": 0}
    monkeypatch.setattr(ky_oauth, "_post_form",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or {"access_token": "t", "sub": "x"})

    resp = client.post('/api/v1/auth/karmayogi/callback',
                       json={"code": "c", "state": "attacker-supplied-state"},
                       headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 400
    assert resp.get_json()['error']['code'] == 'INVALID_STATE'
    # No token exchange was attempted for an unrecognized state.
    assert called["n"] == 0


def test_callback_rejects_state_belonging_to_another_user(app, oauth_env, monkeypatch):
    client = app.test_client()
    _, token_a, user_b, token_b = _make_users(app)
    state = _start_flow(client, token_a)

    monkeypatch.setattr(ky_oauth, "_post_form", lambda *a, **k: {"access_token": "t", "sub": "x"})
    resp = client.post('/api/v1/auth/karmayogi/callback',
                       json={"code": "c", "state": state},
                       headers={'Authorization': f'Bearer {token_b}'})
    assert resp.status_code == 400
    assert resp.get_json()['error']['code'] == 'INVALID_STATE'
    with app.app_context():
        assert User.query.get(user_b).karmayogi_user_id is None


def test_callback_state_is_single_use(app, oauth_env, monkeypatch):
    client = app.test_client()
    _, token, _, _ = _make_users(app)
    state = _start_flow(client, token)
    monkeypatch.setattr(ky_oauth, "_post_form", lambda *a, **k: {"access_token": "t", "sub": "ky-1"})
    monkeypatch.setattr(ky_oauth, "fetch_userinfo", lambda *a, **k: None)
    headers = {'Authorization': f'Bearer {token}'}

    assert client.post('/api/v1/auth/karmayogi/callback',
                       json={"code": "c", "state": state}, headers=headers).status_code == 200
    replay = client.post('/api/v1/auth/karmayogi/callback',
                         json={"code": "c", "state": state}, headers=headers)
    assert replay.status_code == 400
    assert replay.get_json()['error']['code'] == 'INVALID_STATE'


def test_callback_rejects_expired_state(app, oauth_env, monkeypatch):
    from datetime import datetime, timedelta
    client = app.test_client()
    _, token, _, _ = _make_users(app)
    state = _start_flow(client, token)
    with app.app_context():
        row = OAuthState.query.filter_by(state=state).one()
        row.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()

    monkeypatch.setattr(ky_oauth, "_post_form", lambda *a, **k: {"access_token": "t", "sub": "x"})
    resp = client.post('/api/v1/auth/karmayogi/callback',
                       json={"code": "c", "state": state},
                       headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 400
    assert resp.get_json()['error']['code'] == 'STATE_EXPIRED'


def test_callback_surfaces_provider_oauth_error(app, oauth_env, monkeypatch):
    client = app.test_client()
    _, token, _, _ = _make_users(app)
    state = _start_flow(client, token)

    def boom(*a, **k):
        raise OAuthError("Invalid code verifier", details={"oauth_error": "invalid_grant"})

    monkeypatch.setattr(ky_oauth, "_post_form", boom)
    resp = client.post('/api/v1/auth/karmayogi/callback',
                       json={"code": "bad", "state": state},
                       headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 502
    err = resp.get_json()['error']
    assert err['code'] == 'KARMAYOGI_OAUTH_ERROR'
    assert err['details']['oauth_error'] == 'invalid_grant'


def test_callback_reports_unresolved_identity(app, oauth_env, monkeypatch):
    client = app.test_client()
    user_id, token, _, _ = _make_users(app)
    state = _start_flow(client, token)
    monkeypatch.setattr(ky_oauth, "_post_form", lambda *a, **k: {"access_token": "t"})
    monkeypatch.setattr(ky_oauth, "fetch_userinfo", lambda *a, **k: None)

    resp = client.post('/api/v1/auth/karmayogi/callback',
                       json={"code": "c", "state": state},
                       headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 502
    assert resp.get_json()['error']['code'] == 'IDENTITY_UNRESOLVED'
    with app.app_context():
        assert User.query.get(user_id).karmayogi_user_id is None


def test_callback_requires_code_and_state(app, oauth_env):
    client = app.test_client()
    _, token, _, _ = _make_users(app)
    resp = client.post('/api/v1/auth/karmayogi/callback', json={"code": "c"},
                       headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 400
    assert resp.get_json()['error']['code'] == 'VALIDATION_ERROR'


# --------------------------------------------------------------------------- #
# Client credentials (server-to-server)
# --------------------------------------------------------------------------- #

def test_client_credentials_token_posts_expected_grant(oauth_env, monkeypatch):
    captured = {}

    def fake_post_form(url, body, timeout=5):
        captured.update({"url": url, "body": body})
        return {"access_token": "svc-token", "expires_in": 120}

    monkeypatch.setattr(ky_oauth, "_post_form", fake_post_form)
    payload = ky_oauth.client_credentials_token()
    assert payload["access_token"] == "svc-token"
    assert captured["url"] == TOKEN_URL
    assert captured["body"]["grant_type"] == "client_credentials"
    assert captured["body"]["client_id"] == "assesify-test-client"
    assert captured["body"]["client_secret"] == "test-secret"


def test_service_token_is_cached_until_expiry(oauth_env, monkeypatch):
    calls = {"n": 0}

    def fake_post_form(url, body, timeout=5):
        calls["n"] += 1
        return {"access_token": f"svc-{calls['n']}", "expires_in": 3600}

    monkeypatch.setattr(ky_oauth, "_post_form", fake_post_form)
    assert ky_oauth.get_service_token() == "svc-1"
    assert ky_oauth.get_service_token() == "svc-1"  # served from cache
    assert calls["n"] == 1
    assert ky_oauth.get_service_token(force_refresh=True) == "svc-2"
    assert calls["n"] == 2


def test_service_token_not_cached_when_already_expired(oauth_env, monkeypatch):
    calls = {"n": 0}

    def fake_post_form(url, body, timeout=5):
        calls["n"] += 1
        return {"access_token": "short-lived", "expires_in": 1}  # < skew, so never cached

    monkeypatch.setattr(ky_oauth, "_post_form", fake_post_form)
    ky_oauth.get_service_token()
    ky_oauth.get_service_token()
    assert calls["n"] == 2


def test_service_token_returns_none_and_does_not_raise_when_unreachable(oauth_env, monkeypatch):
    def boom(*a, **k):
        raise OAuthError("unreachable", code="KARMAYOGI_UNAVAILABLE")

    monkeypatch.setattr(ky_oauth, "_post_form", boom)
    assert ky_oauth.get_service_token() is None


def test_client_credentials_token_none_without_config(monkeypatch):
    for var in ("KARMAYOGI_TOKEN_URL", "KARMAYOGI_CLIENT_ID", "KARMAYOGI_CLIENT_SECRET"):
        monkeypatch.delenv(var, raising=False)
    assert ky_oauth.client_credentials_token() is None
    ky_oauth.reset_service_token_cache()
    assert ky_oauth.get_service_token() is None
