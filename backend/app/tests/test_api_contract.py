"""Cross-cutting API contract checks: error envelope (§4.5), observability (§9),
and refresh-token rotation (§8)."""
import json
import os

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('JWT_SECRET_KEY', 'test-jwt-secret')

from app.main import create_app
from app.models.refresh_token import RefreshToken
from app.models.users import db, User


@pytest.fixture
def app():
    app = create_app()
    with app.app_context():
        db.create_all()
    yield app


def _register_and_login(client, email="contract@example.com", password="s3cret-pass"):
    client.post('/api/v1/auth/register', json={
        "email": email, "password": password, "full_name": "Contract User"})
    resp = client.post('/api/v1/auth/login', json={"email": email, "password": password})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _assert_envelope(payload):
    assert isinstance(payload, dict), payload
    assert "error" in payload, payload
    err = payload["error"]
    assert set(("code", "message", "details")) <= set(err), err
    assert isinstance(err["code"], str) and err["code"]
    assert isinstance(err["message"], str) and err["message"]
    assert isinstance(err["details"], dict)


# --------------------------------------------------------------------------- #
# Error envelope (spec §4.5)
# --------------------------------------------------------------------------- #

def test_unknown_route_uses_error_envelope(app):
    resp = app.test_client().get('/api/v1/definitely-not-a-route')
    assert resp.status_code == 404
    _assert_envelope(resp.get_json())
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


def test_method_not_allowed_uses_error_envelope(app):
    resp = app.test_client().get('/api/v1/auth/login')
    assert resp.status_code == 405
    _assert_envelope(resp.get_json())
    assert resp.get_json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_missing_jwt_uses_error_envelope(app):
    """flask-jwt-extended answers with `{"msg": ...}`; the envelope is added on top."""
    resp = app.test_client().get('/api/v1/auth/profile')
    assert resp.status_code == 401
    body = resp.get_json()
    _assert_envelope(body)
    assert body["error"]["code"] == "UNAUTHORIZED"
    # Legacy field preserved so existing frontend error handling keeps working.
    assert body.get("msg")
    assert body["error"]["message"] == body["msg"]


def test_legacy_msg_errors_are_wrapped(app):
    client = app.test_client()
    _register_and_login(client)
    resp = client.post('/api/v1/auth/login', json={
        "email": "contract@example.com", "password": "wrong-password"})
    assert resp.status_code == 401
    body = resp.get_json()
    _assert_envelope(body)
    assert body["msg"] == "Invalid credentials"
    assert body["error"]["message"] == "Invalid credentials"


def test_handler_supplied_envelope_is_not_double_wrapped(app):
    client = app.test_client()
    tokens = _register_and_login(client)
    resp = client.post('/api/v1/auth/karmayogi/link', json={},
                       headers={'Authorization': f"Bearer {tokens['access_token']}"})
    assert resp.status_code == 400
    body = resp.get_json()
    _assert_envelope(body)
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert not isinstance(body["error"].get("error"), dict)


def test_success_responses_are_untouched(app):
    client = app.test_client()
    tokens = _register_and_login(client, email="untouched@example.com")
    resp = client.get('/api/v1/auth/profile',
                      headers={'Authorization': f"Bearer {tokens['access_token']}"})
    assert resp.status_code == 200
    assert "error" not in resp.get_json()


# --------------------------------------------------------------------------- #
# Observability (spec §9)
# --------------------------------------------------------------------------- #

def test_request_id_is_echoed_when_supplied(app):
    resp = app.test_client().get('/', headers={'X-Request-ID': 'trace-abc-123'})
    assert resp.headers['X-Request-ID'] == 'trace-abc-123'


def test_request_id_is_generated_when_absent(app):
    resp = app.test_client().get('/')
    generated = resp.headers.get('X-Request-ID')
    assert generated and len(generated) >= 16
    second = app.test_client().get('/').headers.get('X-Request-ID')
    assert second != generated


def test_request_log_line_is_structured_json(app, caplog):
    import logging
    caplog.set_level(logging.INFO)
    app.test_client().get('/', headers={'X-Request-ID': 'log-check'})
    records = []
    for record in caplog.records:
        try:
            records.append(json.loads(record.getMessage()))
        except Exception:
            continue
    entry = next(r for r in records if r.get("event") == "request" and r.get("request_id") == "log-check")
    assert entry["method"] == "GET"
    assert entry["path"] == "/"
    assert entry["status"] == 200
    assert isinstance(entry["duration_ms"], (int, float))


def test_metrics_endpoint_exposes_prometheus_counters(app):
    client = app.test_client()
    client.get('/')
    client.get('/api/v1/definitely-not-a-route')  # generates a 404
    resp = client.get('/metrics')
    assert resp.status_code == 200
    assert resp.headers['Content-Type'].startswith('text/plain')
    body = resp.get_data(as_text=True)
    assert '# TYPE assesify_requests_total counter' in body
    assert 'assesify_request_errors_total 1' in body
    assert 'assesify_request_duration_ms_total' in body
    assert 'assesify_responses_by_status_total{status="404"} 1' in body


# --------------------------------------------------------------------------- #
# Refresh-token rotation (spec §8)
# --------------------------------------------------------------------------- #

def test_refresh_rotates_and_revokes_the_old_token(app):
    client = app.test_client()
    tokens = _register_and_login(client, email="rotate@example.com")
    old_refresh = tokens['refresh_token']

    resp = client.post('/api/v1/auth/refresh', headers={'Authorization': f'Bearer {old_refresh}'})
    assert resp.status_code == 200
    new_tokens = resp.get_json()
    assert new_tokens['refresh_token'] != old_refresh
    assert new_tokens['access_token']

    # The consumed refresh token is revoked and can no longer be replayed.
    replay = client.post('/api/v1/auth/refresh', headers={'Authorization': f'Bearer {old_refresh}'})
    assert replay.status_code == 401
    _assert_envelope(replay.get_json())

    # ...while the freshly issued one still works.
    again = client.post('/api/v1/auth/refresh',
                        headers={'Authorization': f"Bearer {new_tokens['refresh_token']}"})
    assert again.status_code == 200

    with app.app_context():
        rows = RefreshToken.query.all()
        assert len(rows) == 3  # login + two rotations
        assert sum(1 for r in rows if r.revoked) == 2


def test_access_token_cannot_be_used_to_refresh(app):
    client = app.test_client()
    tokens = _register_and_login(client, email="wrongtype@example.com")
    resp = client.post('/api/v1/auth/refresh',
                       headers={'Authorization': f"Bearer {tokens['access_token']}"})
    assert resp.status_code == 422
    _assert_envelope(resp.get_json())


def test_refresh_requires_a_token(app):
    resp = app.test_client().post('/api/v1/auth/refresh')
    assert resp.status_code == 401
    _assert_envelope(resp.get_json())
