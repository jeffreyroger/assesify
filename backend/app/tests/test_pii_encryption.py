import os
import json

import pytest

# Ensure we use an in-memory sqlite DB for tests
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('JWT_SECRET_KEY', 'test-jwt-secret')

from sqlalchemy import text

from app.main import create_app
from app.models.users import db, User


@pytest.fixture
def app():
    app = create_app()
    with app.app_context():
        db.create_all()
    yield app


def test_email_and_full_name_are_encrypted_at_rest(app):
    """The raw DB column value must not be plaintext (spec §8 PII-at-rest)."""
    with app.app_context():
        user = User(full_name='Jane Doe', password_hash='fakehash')
        user.set_email('jane@example.com')
        db.session.add(user)
        db.session.commit()

        raw = db.session.execute(
            text('SELECT email, full_name, email_lookup_hash FROM users WHERE id = :id'),
            {'id': user.id},
        ).fetchone()

        assert raw.email != 'jane@example.com'
        assert raw.full_name != 'Jane Doe'
        assert raw.email_lookup_hash is not None
        assert 'jane' not in raw.email.lower()

        # ORM-level access still transparently decrypts.
        fetched = User.query.get(user.id)
        assert fetched.email == 'jane@example.com'
        assert fetched.full_name == 'Jane Doe'


def test_find_by_email_uses_lookup_hash(app):
    with app.app_context():
        user = User(full_name='Bob', password_hash='fakehash')
        user.set_email('Bob@Example.com')
        db.session.add(user)
        db.session.commit()

        found = User.find_by_email('bob@example.com')  # different case
        assert found is not None
        assert found.id == user.id

        assert User.find_by_email('nobody@example.com') is None


def test_register_and_login_end_to_end(app):
    client = app.test_client()

    resp = client.post('/api/v1/auth/register', json={
        'email': 'newuser@example.com',
        'full_name': 'New User',
        'password': 'StrongPass123!',
    })
    assert resp.status_code == 201

    # duplicate registration rejected via the hash-based uniqueness check
    dup = client.post('/api/v1/auth/register', json={
        'email': 'newuser@example.com',
        'full_name': 'New User Again',
        'password': 'StrongPass123!',
    })
    assert dup.status_code == 400

    login = client.post('/api/v1/auth/login', json={
        'email': 'newuser@example.com',
        'password': 'StrongPass123!',
    })
    assert login.status_code == 200
    body = login.get_json()
    assert body['email'] == 'newuser@example.com'
    assert 'access_token' in body

    with app.app_context():
        raw = db.session.execute(
            text("SELECT email FROM users WHERE email_lookup_hash IS NOT NULL")
        ).fetchall()
        assert all(r.email != 'newuser@example.com' for r in raw)
