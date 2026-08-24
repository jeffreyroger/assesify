"""Verifies that the legacy `/teacher/materials` upload+generate+persist flow
now writes relational `Question` rows (the same schema used by
`/api/v1/materials` + `/api/v1/quizzes` + attempts/scoring/mastery) instead of
only the deprecated `Quiz.questions` JSON blob, and that `Quiz.to_dict()`
still serves the legacy JSON shape the frontend quiz-taking page expects,
regardless of which write path created the quiz.
"""
import io
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('JWT_SECRET_KEY', 'test-jwt-secret')

import pytest
from flask_jwt_extended import create_access_token

from app.main import create_app
from app.models.assessment import Question
from app.models.lesson import Lesson
from app.models.quiz import Quiz
from app.models.users import User, db


@pytest.fixture
def app():
    app = create_app()
    with app.app_context():
        db.create_all()
    yield app


def _teacher_token(app):
    with app.app_context():
        teacher = User(email='legacy_teacher@example.com', full_name='Teacher',
                        password_hash='fakehash', is_teacher=True)
        db.session.add(teacher)
        db.session.commit()
        return create_access_token(identity=str(teacher.id))


def test_legacy_teacher_materials_writes_relational_questions(app):
    token = _teacher_token(app)
    client = app.test_client()

    material_text = (
        b"Budgeting is the process of creating a plan to spend your money. "
        b"This spending plan is called a budget."
    )
    data = {
        "file": (io.BytesIO(material_text), "budgeting.txt"),
        "title": "Budgeting Basics",
        "subject": "budgeting",
    }
    resp = client.post(
        "/api/v1/teacher/materials",
        data=data,
        content_type="multipart/form-data",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = resp.get_json()
    quiz_id = body["quiz_id"]

    with app.app_context():
        # The relational path is now the source of truth: the legacy write
        # site must have created Question rows for this quiz.
        questions = Question.query.filter_by(quiz_id=quiz_id).all()
        assert len(questions) > 0
        assert all(q.competency_tag == "budgeting" for q in questions)

        # The JSON blob column is no longer written to (kept only as a
        # deprecated fallback for pre-migration data).
        quiz = Quiz.query.get(quiz_id)
        assert quiz.questions == []

        # But Quiz.to_dict() still serves the legacy shape the quiz-taking
        # frontend page expects, derived from the relational rows.
        as_dict = quiz.to_dict()
        assert len(as_dict["questions"]) == len(questions)
        for item in as_dict["questions"]:
            assert set(item.keys()) == {"question", "options", "correct_answer", "answer", "hint"}


def test_quiz_to_dict_falls_back_to_json_blob_when_no_relational_rows(app):
    """Old, pre-migration-style quizzes that only ever had the JSON blob (no
    relational Question rows) must keep working via the JSON-blob fallback.
    """
    with app.app_context():
        lesson = Lesson(title="Arithmetic", content="2+2=4", topic="math")
        db.session.add(lesson)
        db.session.commit()
        lesson_free_quiz = Quiz(lesson_id=lesson.id, questions=[
            {"question": "2+2?", "options": ["3", "4"], "correct_answer": "4", "answer": "math"}
        ])
        db.session.add(lesson_free_quiz)
        db.session.commit()
        as_dict = lesson_free_quiz.to_dict()
        assert as_dict["questions"] == [
            {"question": "2+2?", "options": ["3", "4"], "correct_answer": "4", "answer": "math"}
        ]
