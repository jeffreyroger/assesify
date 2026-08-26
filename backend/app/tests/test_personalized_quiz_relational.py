"""Verifies that the personalized / weekly-test quiz generation paths
(`PersonalizedQuizService`, reached via `POST /api/quizzes/generate-personalized`
and `/generate-weekly-test`) now persist relational `Question` rows instead of
the deprecated `Quiz.questions` JSON blob, that `Quiz.to_dict()` still serves
the exact legacy JSON shape the frontend quiz-taking page consumes, and that
`POST /api/quizzes/:id/submit` supports server-authoritative id-based scoring
while keeping the legacy client-supplied-`is_correct` payload working.

All Gemini calls are mocked — no credentials are used and no network I/O
happens.
"""
import os
from datetime import datetime, timedelta

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
from app.services import personalized_quiz_service as pqs
from app.services.personalized_quiz_service import PersonalizedQuizService

LEGACY_QUESTION_KEYS = {"question", "options", "correct_answer", "answer", "hint"}


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


def _lesson(topic='algebra', title='Linear Equations'):
    lesson = Lesson(
        title=title,
        topic=topic,
        content=(
            "A linear equation is an equation of the first degree. "
            "Solving it means isolating the unknown variable on one side. "
            "The solution is the value that makes both sides equal."
        ),
    )
    db.session.add(lesson)
    db.session.commit()
    return lesson


class _FakeAction:
    """Stand-in for `ml.recommender`'s recommended-action object."""

    def __init__(self, topic):
        self.topic = topic


def _assert_relational_only(quiz_id, expected_tag=None):
    """The quiz must have relational Question rows, an empty JSON blob, and a
    `to_dict()` payload in the unchanged legacy shape."""
    questions = Question.query.filter_by(quiz_id=quiz_id).all()
    assert len(questions) > 0
    if expected_tag is not None:
        assert all(q.competency_tag == expected_tag for q in questions)

    quiz = Quiz.query.get(quiz_id)
    assert quiz.questions == []

    as_dict = quiz.to_dict()
    assert len(as_dict["questions"]) == len(questions)
    for item in as_dict["questions"]:
        assert set(item.keys()) == LEGACY_QUESTION_KEYS
    return questions


def test_personalized_quiz_empty_history_writes_relational_questions(app):
    """No attempt history -> rule-based fallback generator; must go relational."""
    user_id = _student(app, 'pq_empty@example.com')
    with app.app_context():
        _lesson()
        result = PersonalizedQuizService.generate_personalized_quiz(user_id)
        assert result is not None
        _assert_relational_only(result["id"], expected_tag='algebra')


def test_personalized_quiz_gemini_path_writes_relational_questions(app, monkeypatch):
    """The Gemini branch persists relational rows tagged with the action topic."""
    user_id = _student(app, 'pq_gemini@example.com')
    with app.app_context():
        lesson = _lesson(topic='geometry', title='Triangles')
        # A prior attempt so the performance dataframe is non-empty and the
        # service takes the Gemini branch rather than the fallback.
        seed_quiz = Quiz(lesson_id=lesson.id, questions=[])
        db.session.add(seed_quiz)
        db.session.commit()
        db.session.add(QuizAttempt(user_id=user_id, quiz_id=seed_quiz.id, score=40.0,
                                   completed_at=datetime.utcnow()))
        db.session.commit()

        monkeypatch.setattr(pqs, 'recommend_actions',
                            lambda agg_df, sid: [_FakeAction('geometry')])
        monkeypatch.setattr(pqs, 'generate_quiz_from_action', lambda client, action, n_questions=5: {
            'quiz': [
                {
                    'question': 'How many sides does a triangle have?',
                    'choices': ['2', '3', '4', '5'],
                    'correct_answer': '3',
                    'answer': 'A triangle is a three-sided polygon.',
                },
                {
                    'question': 'What do the interior angles of a triangle sum to?',
                    'options': ['90', '180', '270', '360'],
                    'correct_answer': '180',
                    'answer': 'Euclidean triangles always sum to 180 degrees.',
                },
            ]
        })

        result = PersonalizedQuizService.generate_personalized_quiz(user_id)
        assert result is not None
        questions = _assert_relational_only(result["id"], expected_tag='geometry')
        assert len(questions) == 2
        # 'choices' is still normalized to 'options' before persisting.
        first = next(q for q in questions if q.stem.startswith('How many sides'))
        assert [opt['text'] for opt in first.options] == ['2', '3', '4', '5']
        assert first.correct_keys == ['B']


def test_weekly_test_no_activity_writes_relational_questions(app):
    """No activity in the window -> general fallback quiz, relational."""
    user_id = _student(app, 'wk_empty@example.com')
    with app.app_context():
        _lesson(topic='calculus', title='Limits')
        end = datetime.utcnow()
        start = end - timedelta(days=7)
        result = PersonalizedQuizService.generate_weekly_test(user_id, 5, start, end)
        assert result is not None
        _assert_relational_only(result["id"], expected_tag='calculus')


def test_weekly_test_tags_questions_with_their_own_topic(app, monkeypatch):
    """The multi-topic weekly test tags each question group with its topic."""
    user_id = _student(app, 'wk_topics@example.com')
    with app.app_context():
        lesson = _lesson(topic='algebra', title='Quadratics')
        # A legacy blob-only quiz: also exercises question_count()'s fallback.
        seed_quiz = Quiz(lesson_id=lesson.id, questions=[
            {"question": "x?", "options": ["1", "2"], "correct_answer": "1", "answer": "n/a"}
        ])
        db.session.add(seed_quiz)
        db.session.commit()
        db.session.add(QuizAttempt(user_id=user_id, quiz_id=seed_quiz.id, score=30.0,
                                   completed_at=datetime.utcnow()))
        db.session.commit()

        monkeypatch.setattr(pqs.GeminiClient, 'generate_json', lambda self, prompt: {
            'quiz': [
                {
                    'question': 'Which expression is quadratic?',
                    'options': ['x + 1', 'x^2 + 1', '1/x', 'sqrt(x)'],
                    'correct_answer': 'x^2 + 1',
                    'answer': 'Degree two makes it quadratic.',
                }
            ]
        })

        end = datetime.utcnow() + timedelta(minutes=1)
        start = end - timedelta(days=7)
        result = PersonalizedQuizService.generate_weekly_test(user_id, 3, start, end)
        assert result is not None
        assert result['is_weekly_test'] is True
        questions = _assert_relational_only(result["id"], expected_tag='algebra')
        assert questions[0].correct_keys == ['B']


def test_submit_scores_server_side_when_question_id_is_supplied(app):
    """A client claiming `is_correct: true` is overridden by the stored answer."""
    user_id = _student(app, 'submit_ids@example.com')
    with app.app_context():
        lesson = _lesson()
        result = PersonalizedQuizService.generate_personalized_quiz(user_id)
        quiz_id = result["id"]
        rows = Question.query.filter_by(quiz_id=quiz_id).order_by(Question.id).all()
        first = rows[0]
        wrong_key = next(opt['key'] for opt in first.options
                         if opt['key'] not in (first.correct_keys or []))
        payload = {
            "answers": [
                {"question_id": first.id, "selected_keys": first.correct_keys},
                {"question_id": first.id, "selected_keys": [wrong_key], "is_correct": True},
            ]
        }
        token = create_access_token(identity=str(user_id))

    client = app.test_client()
    resp = client.post(f"/api/quizzes/{quiz_id}/submit", json=payload,
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201
    # Server-side grading: exactly one of the two is right, so 50% — the
    # client's lied-about `is_correct: True` on the second answer is ignored.
    assert resp.get_json()["score"] == 50.0


def test_submit_still_accepts_the_legacy_client_supplied_payload(app):
    """No `question_id` -> the pre-existing contract is preserved verbatim."""
    user_id = _student(app, 'submit_legacy@example.com')
    with app.app_context():
        lesson = _lesson()
        quiz = Quiz(lesson_id=lesson.id, questions=[
            {"question": "2+2?", "options": ["3", "4"], "correct_answer": "4", "answer": "math"}
        ])
        db.session.add(quiz)
        db.session.commit()
        quiz_id = quiz.id
        token = create_access_token(identity=str(user_id))

    client = app.test_client()
    resp = client.post(f"/api/quizzes/{quiz_id}/submit", json={
        "answers": [
            {"question": "2+2?", "answer": "4", "is_correct": True},
            {"question": "3+3?", "answer": "5", "is_correct": False},
        ]
    }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["score"] == 50.0

    with app.app_context():
        attempt = QuizAttempt.query.get(body["attempt_id"])
        stored = {a.question_text: a.is_correct for a in attempt.answers}
        assert stored == {"2+2?": True, "3+3?": False}
