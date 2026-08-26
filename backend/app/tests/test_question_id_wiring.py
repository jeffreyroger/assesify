"""End-to-end wiring of the relational `Question.id` through the legacy quiz
shape the frontend consumes.

`app/services/quiz_generation.py::legacy_shape_from_questions()` previously
omitted `id`, so `GET /api/quizzes/:id` never told the client which relational
row a question came from. That made the frontend's `question_id`-bearing
autosave payload dead code (it guarded on `question.id`) and left
`POST /api/quizzes/:id/submit` stuck on the legacy client-supplied
`is_correct`. These tests pin the id down the whole path: emitted by the read
shape, accepted by `/api/v1/<attempt>/responses`, and honoured by the
server-authoritative grading in `/api/quizzes/:id/submit`.

No Gemini, no credentials, no network.
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('JWT_SECRET_KEY', 'test-jwt-secret')

import pytest
from flask_jwt_extended import create_access_token

from app.main import create_app
from app.models.assessment import Question
from app.models.lesson import Lesson
from app.models.quiz import Quiz
from app.models.submission import QuizAttempt
from app.models.users import User, db
from app.services.quiz_generation import persist_quiz_questions

GENERATED = [
    {"question": "2+2?", "options": ["3", "4"], "correct_answer": "4", "answer": "arithmetic"},
    {"question": "Capital of France?", "options": ["Paris", "Berlin"],
     "correct_answer": "Paris", "answer": "geography"},
]


@pytest.fixture
def app():
    app = create_app()
    with app.app_context():
        db.create_all()
    yield app


def _student(app, email):
    with app.app_context():
        student = User(email=email, full_name='Student',
                       password_hash='fakehash', is_teacher=False)
        db.session.add(student)
        db.session.commit()
        return student.id


def _relational_quiz():
    lesson = Lesson(title="Basics", content="2+2=4", topic="math")
    db.session.add(lesson)
    db.session.flush()
    quiz = Quiz(lesson_id=lesson.id, questions=[])
    db.session.add(quiz)
    db.session.flush()
    persist_quiz_questions(quiz.id, GENERATED, competency_tag="math")
    db.session.commit()
    return quiz


def test_legacy_question_shape_exposes_the_relational_id(app):
    """`Quiz.to_dict()` must carry each question's relational id alongside the
    unchanged legacy keys, so the client can reference it later."""
    with app.app_context():
        quiz = _relational_quiz()
        rows = Question.query.filter_by(quiz_id=quiz.id).order_by(Question.id).all()
        items = quiz.to_dict(include_answers=True)["questions"]

        assert [item["id"] for item in items] == [row.id for row in rows]
        assert all(item["id"] is not None for item in items)
        # Legacy keys untouched (teacher view).
        first = items[0]
        assert first["question"] == "2+2?"
        assert first["options"] == ["3", "4"]
        assert first["correct_answer"] == "4"
        assert first["answer"] == "arithmetic"
        assert first["hint"] == ""


def test_autosave_accepts_the_id_from_the_legacy_shape(app):
    """The id served to the client round-trips into `/api/v1/<attempt>/responses`."""
    user_id = _student(app, 'autosave_id@example.com')
    with app.app_context():
        quiz = _relational_quiz()
        quiz_id = quiz.id
        served_id = quiz.to_dict()["questions"][0]["id"]
        token = create_access_token(identity=str(user_id))

    client = app.test_client()
    headers = {"Authorization": f"Bearer {token}"}
    started = client.post(f"/api/v1/quizzes/{quiz_id}/attempts", headers=headers)
    assert started.status_code == 201
    attempt_id = started.get_json()["id"]

    saved = client.post(f"/api/v1/{attempt_id}/responses",
                        json={"question_id": served_id, "selected_keys": ["B"]},
                        headers=headers)
    assert saved.status_code == 200
    assert saved.get_json() == {"question_id": served_id, "is_correct": True}


def test_submit_with_question_id_and_answer_text_overrides_a_lying_client(app):
    """The exact payload the frontend now sends (question_id + selected_keys +
    the legacy fields) is graded server-side; a client claiming a wrong answer
    is correct is scored wrong anyway."""
    user_id = _student(app, 'submit_id_wiring@example.com')
    with app.app_context():
        quiz = _relational_quiz()
        quiz_id = quiz.id
        items = quiz.to_dict()["questions"]
        payload = {
            "user_id": 1,  # ignored; identity comes from the JWT
            "answers": [
                # Right answer, but the client claims it is wrong.
                {"question_id": items[0]["id"], "selected_keys": ["B"],
                 "question": items[0]["question"], "answer": "4", "is_correct": False},
                # Wrong answer, but the client claims it is right.
                {"question_id": items[1]["id"], "selected_keys": ["B"],
                 "question": items[1]["question"], "answer": "Berlin", "is_correct": True},
            ],
        }
        token = create_access_token(identity=str(user_id))

    client = app.test_client()
    resp = client.post(f"/api/quizzes/{quiz_id}/submit", json=payload,
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201
    body = resp.get_json()
    # Server-authoritative: first right, second wrong -> 50%, both client
    # `is_correct` flags ignored.
    assert body["score"] == 50.0

    with app.app_context():
        attempt = QuizAttempt.query.get(body["attempt_id"])
        stored = {a.question_text: (a.is_correct, a.student_answer_text)
                  for a in attempt.answers}
        assert stored == {
            "2+2?": (True, "4"),
            "Capital of France?": (False, "Berlin"),
        }


def test_submit_without_question_id_still_uses_the_legacy_client_flags(app):
    """Any client that does not send `question_id` scores exactly as before."""
    user_id = _student(app, 'submit_no_id@example.com')
    with app.app_context():
        quiz = _relational_quiz()
        quiz_id = quiz.id
        token = create_access_token(identity=str(user_id))

    client = app.test_client()
    resp = client.post(f"/api/quizzes/{quiz_id}/submit", json={
        "answers": [
            {"question": "2+2?", "answer": "Submitted via API", "is_correct": True},
            {"question": "Capital of France?", "answer": "Submitted via API",
             "is_correct": False},
        ]
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201
    assert resp.get_json()["score"] == 50.0
