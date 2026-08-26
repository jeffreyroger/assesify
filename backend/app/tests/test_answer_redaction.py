"""Students must never receive the answers to questions they have not answered.

`GET /api/quizzes/:id` used to serve `correct_answer` (and `answer`, the
explanation) for every question, so any student could read the whole answer key
out of the network tab before answering a thing (spec §4.3 "Full quiz (teacher
view) or sanitized (student)", §8 authz).

The read payload is now sanitized for everyone except the teacher who owns the
quiz's lesson, and the immediate-feedback UX is preserved by
`POST /api/quizzes/<quiz_id>/questions/<question_id>/check`, which reveals one
question's answer only once the student has committed a selection.

No Gemini, no credentials, no network.
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('JWT_SECRET_KEY', 'test-jwt-secret')

import pytest
from flask_jwt_extended import create_access_token

from app.main import create_app
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

REVEALING_KEYS = ("correct_answer", "answer")


@pytest.fixture
def app():
    app = create_app()
    with app.app_context():
        db.create_all()
    yield app


def _user(app, email, is_teacher=False):
    with app.app_context():
        user = User(email=email, full_name='Someone',
                    password_hash='fakehash', is_teacher=is_teacher)
        db.session.add(user)
        db.session.commit()
        return user.id


def _quiz(teacher_id=None):
    lesson = Lesson(title="Basics", content="2+2=4", topic="math", teacher_id=teacher_id)
    db.session.add(lesson)
    db.session.flush()
    quiz = Quiz(lesson_id=lesson.id, questions=[])
    db.session.add(quiz)
    db.session.flush()
    persist_quiz_questions(quiz.id, GENERATED, competency_tag="math")
    db.session.commit()
    return quiz


def _token(app, user_id):
    with app.app_context():
        return create_access_token(identity=str(user_id))


def test_student_payload_carries_no_answers_for_unanswered_questions(app):
    student_id = _user(app, 'redact_student@example.com')
    with app.app_context():
        quiz_id = _quiz().id
    client = app.test_client()

    resp = client.get(f"/api/quizzes/{quiz_id}",
                      headers={"Authorization": f"Bearer {_token(app, student_id)}"})
    assert resp.status_code == 200
    items = resp.get_json()["questions"]
    assert len(items) == len(GENERATED)
    for item in items:
        assert set(item.keys()) == {"id", "question", "options", "hint"}
        for key in REVEALING_KEYS:
            assert key not in item
    # The stems and options the student needs in order to answer are all there.
    assert [item["question"] for item in items] == ["2+2?", "Capital of France?"]
    assert items[0]["options"] == ["3", "4"]
    # And nowhere in the raw body does the answer key leak.
    assert b'"correct_answer"' not in resp.data


def test_anonymous_reader_also_gets_the_sanitized_payload(app):
    """The endpoint has always been open to unauthenticated callers; they get
    the student view, never the answer key."""
    with app.app_context():
        quiz_id = _quiz().id
    resp = app.test_client().get(f"/api/quizzes/{quiz_id}")
    assert resp.status_code == 200
    for item in resp.get_json()["questions"]:
        assert "correct_answer" not in item


def test_owning_teacher_still_sees_the_full_answer_key(app):
    teacher_id = _user(app, 'redact_teacher@example.com', is_teacher=True)
    with app.app_context():
        quiz_id = _quiz(teacher_id=teacher_id).id

    resp = app.test_client().get(
        f"/api/quizzes/{quiz_id}",
        headers={"Authorization": f"Bearer {_token(app, teacher_id)}"})
    assert resp.status_code == 200
    items = resp.get_json()["questions"]
    assert set(items[0].keys()) == {"id", "question", "options", "correct_answer", "answer", "hint"}
    assert items[0]["correct_answer"] == "4"
    assert items[0]["answer"] == "arithmetic"


def test_teacher_who_does_not_own_the_quiz_gets_the_sanitized_payload(app):
    owner_id = _user(app, 'redact_owner@example.com', is_teacher=True)
    other_id = _user(app, 'redact_other_teacher@example.com', is_teacher=True)
    with app.app_context():
        quiz_id = _quiz(teacher_id=owner_id).id

    resp = app.test_client().get(
        f"/api/quizzes/{quiz_id}",
        headers={"Authorization": f"Bearer {_token(app, other_id)}"})
    assert resp.status_code == 200
    assert "correct_answer" not in resp.get_json()["questions"][0]




def _start_attempt(client, quiz_id, headers):
    resp = client.post(f"/api/v1/quizzes/{quiz_id}/attempts", headers=headers)
    assert resp.status_code == 201
    return resp.get_json()["id"]


def _answer(client, attempt_id, question_id, keys, headers):
    return client.post(f"/api/v1/{attempt_id}/responses", headers=headers,
                       json={"question_id": question_id, "selected_keys": keys})


def test_check_endpoint_reveals_one_question_after_it_is_answered(app):
    student_id = _user(app, 'check_ok@example.com')
    with app.app_context():
        quiz = _quiz()
        quiz_id = quiz.id
        ids = [item["id"] for item in quiz.to_dict()["questions"]]
    client = app.test_client()
    headers = {"Authorization": f"Bearer {_token(app, student_id)}"}
    attempt_id = _start_attempt(client, quiz_id, headers)

    # Correct pick, recorded first.
    assert _answer(client, attempt_id, ids[0], ["B"], headers).status_code == 200
    right = client.post(f"/api/quizzes/{quiz_id}/questions/{ids[0]}/check",
                        json={"attempt_id": attempt_id}, headers=headers)
    assert right.status_code == 200
    assert right.get_json() == {"question_id": ids[0], "is_correct": True,
                                "correct_answer": "4", "correct_keys": ["B"],
                                "explanation": "arithmetic"}

    # A wrong pick still reveals that one question's answer, and only that one.
    _answer(client, attempt_id, ids[1], ["B"], headers)
    wrong = client.post(f"/api/quizzes/{quiz_id}/questions/{ids[1]}/check",
                        json={"attempt_id": attempt_id}, headers=headers)
    body = wrong.get_json()
    assert wrong.status_code == 200
    assert body["is_correct"] is False
    assert body["correct_answer"] == "Paris"
    assert body["question_id"] == ids[1]


def test_check_refuses_to_reveal_a_question_the_student_has_not_answered(app):
    """The harvesting attack: without this the endpoint is an answer-key oracle."""
    student_id = _user(app, 'check_harvest@example.com')
    with app.app_context():
        quiz = _quiz()
        quiz_id = quiz.id
        ids = [item["id"] for item in quiz.to_dict()["questions"]]
    client = app.test_client()
    headers = {"Authorization": f"Bearer {_token(app, student_id)}"}
    attempt_id = _start_attempt(client, quiz_id, headers)

    for question_id in ids:
        resp = client.post(f"/api/quizzes/{quiz_id}/questions/{question_id}/check",
                           json={"attempt_id": attempt_id}, headers=headers)
        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "ANSWER_REQUIRED"
        assert b"correct_answer" not in resp.data


def test_check_rejects_another_students_attempt(app):
    owner_id = _user(app, 'check_owner@example.com')
    intruder_id = _user(app, 'check_intruder@example.com')
    with app.app_context():
        quiz = _quiz()
        quiz_id = quiz.id
        question_id = quiz.to_dict()["questions"][0]["id"]
    client = app.test_client()
    owner_headers = {"Authorization": f"Bearer {_token(app, owner_id)}"}
    attempt_id = _start_attempt(client, quiz_id, owner_headers)
    _answer(client, attempt_id, question_id, ["B"], owner_headers)

    resp = client.post(f"/api/quizzes/{quiz_id}/questions/{question_id}/check",
                       json={"attempt_id": attempt_id},
                       headers={"Authorization": f"Bearer {_token(app, intruder_id)}"})
    assert resp.status_code == 403
    assert resp.get_json()["error"]["code"] == "FORBIDDEN"
    assert b"correct_answer" not in resp.data


def test_check_rejects_an_attempt_belonging_to_a_different_quiz(app):
    student_id = _user(app, 'check_wrongquiz@example.com')
    with app.app_context():
        quiz_a = _quiz()
        quiz_a_id, question_id = quiz_a.id, quiz_a.to_dict()["questions"][0]["id"]
        quiz_b_id = _quiz().id
    client = app.test_client()
    headers = {"Authorization": f"Bearer {_token(app, student_id)}"}
    other_attempt = _start_attempt(client, quiz_b_id, headers)

    resp = client.post(f"/api/quizzes/{quiz_a_id}/questions/{question_id}/check",
                       json={"attempt_id": other_attempt}, headers=headers)
    assert resp.status_code == 404
    assert b"correct_answer" not in resp.data


def test_check_rejects_a_question_id_from_another_quiz(app):
    student_id = _user(app, 'check_cross@example.com')
    with app.app_context():
        quiz_a_id = _quiz().id
        quiz_b = _quiz()
        foreign_id = quiz_b.to_dict()["questions"][0]["id"]
    assert foreign_id is not None
    client = app.test_client()
    headers = {"Authorization": f"Bearer {_token(app, student_id)}"}
    attempt_id = _start_attempt(client, quiz_a_id, headers)

    resp = client.post(f"/api/quizzes/{quiz_a_id}/questions/{foreign_id}/check",
                       json={"attempt_id": attempt_id}, headers=headers)
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"
    assert b"correct_answer" not in resp.data


def test_check_requires_auth_and_an_attempt_id(app):
    student_id = _user(app, 'check_guard@example.com')
    with app.app_context():
        quiz = _quiz()
        quiz_id, question_id = quiz.id, quiz.to_dict()["questions"][0]["id"]
    client = app.test_client()

    anon = client.post(f"/api/quizzes/{quiz_id}/questions/{question_id}/check",
                       json={"attempt_id": 1})
    assert anon.status_code == 401

    empty = client.post(f"/api/quizzes/{quiz_id}/questions/{question_id}/check",
                        json={},
                        headers={"Authorization": f"Bearer {_token(app, student_id)}"})
    assert empty.status_code == 400
    assert empty.get_json()["error"]["code"] == "VALIDATION_ERROR"
    assert b"correct_answer" not in empty.data


def test_revealed_answer_is_locked_and_cannot_be_changed(app):
    """First selection wins: harvest-then-resubmit must not improve the score."""
    student_id = _user(app, 'check_lock@example.com')
    with app.app_context():
        quiz = _quiz()
        quiz_id = quiz.id
        ids = [item["id"] for item in quiz.to_dict()["questions"]]
    client = app.test_client()
    headers = {"Authorization": f"Bearer {_token(app, student_id)}"}
    attempt_id = _start_attempt(client, quiz_id, headers)

    # Guess wrong on both (q0's answer is "B"/"4", q1's is "A"/"Paris"), then
    # look at the answers.
    for question_id, wrong_key in zip(ids, ["A", "B"]):
        _answer(client, attempt_id, question_id, [wrong_key], headers)
        assert client.post(f"/api/quizzes/{quiz_id}/questions/{question_id}/check",
                           json={"attempt_id": attempt_id},
                           headers=headers).status_code == 200

    # The autosave path now refuses to overwrite the revealed answers ...
    retry = _answer(client, attempt_id, ids[0], ["B"], headers)
    assert retry.status_code == 409
    assert retry.get_json()["error"]["code"] == "ANSWER_LOCKED"

    # ... and re-submitting with the harvested answers still scores 0.
    submitted = client.post(f"/api/quizzes/{quiz_id}/submit", headers=headers, json={
        "answers": [
            {"question_id": ids[0], "selected_keys": ["B"], "answer": "4", "is_correct": True},
            {"question_id": ids[1], "selected_keys": ["A"], "answer": "Paris",
             "is_correct": True},
        ]
    })
    assert submitted.status_code == 201
    assert submitted.get_json()["score"] == 0.0


def test_the_score_of_record_stays_server_computed(app):
    """The submitted score is recomputed from the stored correct_keys, never
    taken from the client."""
    student_id = _user(app, 'check_score@example.com')
    with app.app_context():
        quiz = _quiz()
        quiz_id = quiz.id
        ids = [item["id"] for item in quiz.to_dict()["questions"]]
    client = app.test_client()
    headers = {"Authorization": f"Bearer {_token(app, student_id)}"}

    # One right, one wrong -- and the client lies about both.
    submitted = client.post(f"/api/quizzes/{quiz_id}/submit", headers=headers, json={
        "answers": [
            {"question_id": ids[0], "selected_keys": ["B"], "question": "2+2?",
             "answer": "4", "is_correct": False},
            {"question_id": ids[1], "selected_keys": ["B"],
             "question": "Capital of France?", "answer": "Berlin", "is_correct": True},
        ]
    })
    assert submitted.status_code == 201
    body = submitted.get_json()
    assert body["score"] == 50.0
    with app.app_context():
        assert QuizAttempt.query.get(body["attempt_id"]).score == 50.0
