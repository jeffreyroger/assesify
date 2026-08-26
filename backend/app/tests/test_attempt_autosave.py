"""The authenticated attempt + autosave path (spec §4.3, §7).

The quiz-taking page starts an attempt with a bearer token, autosaves one
`responses` row per question, and then submits through the *legacy*
`POST /api/quizzes/<id>/submit` endpoint. These tests pin the two properties
that reconciliation has to preserve:

1. The score of record and the gamification payload come from the legacy
   endpoint, exactly as before authentication was wired in.
2. The open attempt is reused rather than duplicated, so the autosaved
   item-level responses end up attached to the attempt that was scored.
"""
import pytest
from flask_jwt_extended import create_access_token

from app.main import create_app
from app.models.assessment import Response
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
        user = User(email=email, full_name='Student', password_hash='fakehash')
        db.session.add(user)
        db.session.commit()
        return user.id


def _quiz(app):
    with app.app_context():
        lesson = Lesson(title="Basics", content="2+2=4", topic="math")
        db.session.add(lesson)
        db.session.flush()
        quiz = Quiz(lesson_id=lesson.id, questions=[])
        db.session.add(quiz)
        db.session.flush()
        persist_quiz_questions(quiz.id, GENERATED, competency_tag="math")
        db.session.commit()
        return quiz.id, [item["id"] for item in quiz.to_dict()["questions"]]


def _headers(app, user_id):
    with app.app_context():
        return {"Authorization": f"Bearer {create_access_token(identity=str(user_id))}"}


def test_authenticated_attempt_start_persists_a_real_response_row(app):
    student_id = _student(app, 'autosave@example.com')
    quiz_id, ids = _quiz(app)
    client = app.test_client()
    headers = _headers(app, student_id)

    started = client.post(f"/api/v1/quizzes/{quiz_id}/attempts", headers=headers)
    assert started.status_code == 201
    attempt_id = started.get_json()["id"]

    saved = client.post(f"/api/v1/{attempt_id}/responses", headers=headers,
                        json={"question_id": ids[0], "selected_keys": ["B"]})
    assert saved.status_code == 200
    assert saved.get_json() == {"question_id": ids[0], "is_correct": True}

    with app.app_context():
        rows = Response.query.filter_by(attempt_id=attempt_id).all()
        assert len(rows) == 1
        assert rows[0].question_id == ids[0]
        assert rows[0].selected_keys == ["B"]
        assert rows[0].is_correct is True


def test_attempt_start_requires_authentication(app):
    quiz_id, _ = _quiz(app)
    assert app.test_client().post(f"/api/v1/quizzes/{quiz_id}/attempts").status_code == 401


def test_legacy_submit_reuses_the_open_attempt_and_still_awards_gamification(app):
    student_id = _student(app, 'reuse@example.com')
    quiz_id, ids = _quiz(app)
    client = app.test_client()
    headers = _headers(app, student_id)

    attempt_id = client.post(f"/api/v1/quizzes/{quiz_id}/attempts",
                             headers=headers).get_json()["id"]
    for question_id, keys in zip(ids, [["B"], ["B"]]):  # one right, one wrong
        client.post(f"/api/v1/{attempt_id}/responses", headers=headers,
                    json={"question_id": question_id, "selected_keys": keys})

    submitted = client.post(f"/api/quizzes/{quiz_id}/submit", headers=headers, json={
        "answers": [
            {"question_id": ids[0], "selected_keys": ["B"], "question": "2+2?", "answer": "4"},
            {"question_id": ids[1], "selected_keys": ["B"],
             "question": "Capital of France?", "answer": "Berlin"},
        ]
    })
    assert submitted.status_code == 201
    body = submitted.get_json()
    assert body["score"] == 50.0
    # Gamification is unchanged: the legacy endpoint is still the one scoring.
    assert body["diamonds_earned"] == 5
    assert body["health"] == 4
    assert body["streak"] == 1

    with app.app_context():
        attempts = QuizAttempt.query.filter_by(user_id=student_id, quiz_id=quiz_id).all()
        # One quiz-taking session, one attempt row - not one per endpoint.
        assert len(attempts) == 1
        assert attempts[0].id == attempt_id
        assert attempts[0].score == 50.0
        # Completion is what makes it visible to mastery/weekly-performance.
        assert attempts[0].completed_at is not None
        # The autosaved item-level responses are attached to the scored attempt.
        assert Response.query.filter_by(attempt_id=attempt_id).count() == 2


def test_submit_without_an_open_attempt_still_creates_one(app):
    """No regression for a client that never starts an attempt (anonymous
    page load, legacy client)."""
    student_id = _student(app, 'noattempt@example.com')
    quiz_id, ids = _quiz(app)
    headers = _headers(app, student_id)

    submitted = app.test_client().post(f"/api/quizzes/{quiz_id}/submit", headers=headers, json={
        "answers": [
            {"question_id": ids[0], "selected_keys": ["B"], "question": "2+2?", "answer": "4"},
            {"question_id": ids[1], "selected_keys": ["A"],
             "question": "Capital of France?", "answer": "Paris"},
        ]
    })
    assert submitted.status_code == 201
    assert submitted.get_json()["score"] == 100.0
    with app.app_context():
        assert QuizAttempt.query.filter_by(user_id=student_id).count() == 1
