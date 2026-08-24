import io
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('JWT_SECRET_KEY', 'test-jwt-secret')

from app.main import create_app
from app.models.users import db, User
from flask_jwt_extended import create_access_token


def test_upload_txt_file():
    app = create_app()
    with app.app_context():
        db.create_all()
        teacher = User(email='upload_teacher@example.com', full_name='Teacher',
                        password_hash='fakehash', is_teacher=True)
        db.session.add(teacher)
        db.session.commit()
        token = create_access_token(identity=str(teacher.id))

    client = app.test_client()
    data = {
        "file": (io.BytesIO(b"Photosynthesis converts light to chemical energy in plants."), "lesson.txt"),
        "title": "Week 1",
    }
    resp = client.post(
        "/api/v1/materials",
        data=data,
        content_type="multipart/form-data",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["title"] == "Week 1"
    assert body["mime_type"] == "text/plain"
