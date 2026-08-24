import os

import pytest

# Ensure we use an in-memory sqlite DB for tests
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('JWT_SECRET_KEY', 'test-jwt-secret')

from app.main import create_app
from app.models.audit_log import AuditLog
from app.models.users import db, User
from flask_jwt_extended import create_access_token


@pytest.fixture
def app():
    app = create_app()
    with app.app_context():
        db.create_all()
    yield app


def _make_users(app):
    with app.app_context():
        admin = User(email='admin@example.com', full_name='Admin', password_hash='fakehash', is_admin=True)
        student = User(email='student2@example.com', full_name='Student', password_hash='fakehash')
        db.session.add_all([admin, student])
        db.session.commit()
        admin_token = create_access_token(identity=str(admin.id))
        student_token = create_access_token(identity=str(student.id))
        return admin.id, student.id, admin_token, student_token


def test_audit_log_requires_admin_role(app):
    client = app.test_client()
    _admin_id, _student_id, _admin_token, student_token = _make_users(app)

    resp = client.get('/api/v1/admin/audit-log', headers={'Authorization': f'Bearer {student_token}'})
    assert resp.status_code == 403

    resp = client.get('/api/v1/admin/audit-log')
    assert resp.status_code == 401


def test_admin_action_creates_audit_log_entry(app):
    client = app.test_client()
    admin_id, student_id, admin_token, _student_token = _make_users(app)
    headers = {'Authorization': f'Bearer {admin_token}'}

    # Sensitive action: admin viewing another user's data.
    resp = client.get(f'/api/v1/admin/users/{student_id}', headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()['id'] == student_id

    with app.app_context():
        entries = AuditLog.query.all()
        actions = {entry.action for entry in entries}
        assert 'admin_view_user' in actions
        view_entry = next(e for e in entries if e.action == 'admin_view_user')
        assert view_entry.actor_id == admin_id
        assert view_entry.target_type == 'user'
        assert view_entry.target_id == str(student_id)


def test_audit_log_endpoint_lists_entries_desc(app):
    client = app.test_client()
    admin_id, student_id, admin_token, _student_token = _make_users(app)
    headers = {'Authorization': f'Bearer {admin_token}'}

    # Generate a couple of admin-guarded actions.
    client.get(f'/api/v1/admin/users/{student_id}', headers=headers)
    client.get(f'/api/v1/admin/users/{admin_id}', headers=headers)

    resp = client.get('/api/v1/admin/audit-log', headers=headers)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['total'] >= 2
    entries = body['entries']
    assert len(entries) >= 2
    # Newest first.
    timestamps = [entry['created_at'] for entry in entries]
    assert timestamps == sorted(timestamps, reverse=True)
    assert all(entry['actor_id'] == admin_id for entry in entries)
