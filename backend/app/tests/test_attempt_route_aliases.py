"""Spec §4.3 route paths for attempts.

The attempts blueprint was mounted only at `/api/v1`, so its routes resolved to
`/api/v1/<attempt_id>/responses` etc. - missing the `attempts` segment the spec
requires. That was a live bug, not a cosmetic one:
`frontend/app/results/[attemptId]/page.tsx` already fetched
`/api/v1/attempts/<id>/result`, which returned 404, so the student results page
could never render feedback.

The blueprint is now registered under both prefixes, so these tests assert the
spec paths work AND that the legacy paths still return identical results.
"""
import json
import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")

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


@pytest.fixture
def ctx(app):
    with app.app_context():
        user = User(email="alias@example.com", full_name="Alias", password_hash="x")
        db.session.add(user)
        db.session.commit()
        lesson = Lesson(title="L", content="C", topic="Algebra")
        db.session.add(lesson)
        db.session.commit()
        quiz = Quiz(lesson_id=lesson.id, questions=[])
        db.session.add(quiz)
        db.session.commit()
        q1 = Question(quiz_id=quiz.id, stem="2+2?", options=["3", "4"],
                      correct_keys=["B"], explanation="four", competency_tag="Algebra")
        q2 = Question(quiz_id=quiz.id, stem="3+3?", options=["6", "7"],
                      correct_keys=["A"], explanation="six", competency_tag="Algebra")
        db.session.add_all([q1, q2])
        db.session.commit()
        token = create_access_token(identity=str(user.id))
        return {
            "client": app.test_client(),
            "headers": {"Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"},
            "quiz_id": quiz.id,
            "q1": q1.id,
            "q2": q2.id,
        }


def _start(ctx):
    resp = ctx["client"].post(f"/api/v1/quizzes/{ctx['quiz_id']}/attempts",
                              headers=ctx["headers"])
    assert resp.status_code == 201
    return resp.get_json()["id"]


def test_spec_path_responses_submit_result(ctx):
    """The full spec-conformant §4.3 lifecycle under /api/v1/attempts/<id>/..."""
    client, headers = ctx["client"], ctx["headers"]
    attempt_id = _start(ctx)

    resp = client.post(f"/api/v1/attempts/{attempt_id}/responses", headers=headers,
                       data=json.dumps({"question_id": ctx["q1"], "selected_keys": ["B"]}))
    assert resp.status_code == 200
    assert resp.get_json()["is_correct"] is True

    resp = client.get(f"/api/v1/attempts/{attempt_id}/next-question", headers=headers)
    assert resp.status_code == 200

    resp = client.post(f"/api/v1/attempts/{attempt_id}/submit", headers=headers)
    assert resp.status_code == 200
    assert resp.get_json()["correct"] == 1


def test_results_page_path_returns_200(ctx):
    """Regression: GET /api/v1/attempts/<id>/result used to 404.

    frontend/app/results/[attemptId]/page.tsx calls exactly this URL.
    """
    client, headers = ctx["client"], ctx["headers"]
    attempt_id = _start(ctx)
    client.post(f"/api/v1/attempts/{attempt_id}/responses", headers=headers,
                data=json.dumps({"question_id": ctx["q1"], "selected_keys": ["B"]}))
    client.post(f"/api/v1/attempts/{attempt_id}/submit", headers=headers)

    resp = client.get(f"/api/v1/attempts/{attempt_id}/result", headers=headers)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["attempt_id"] == attempt_id
    assert len(body["feedback"]) == 1
    assert body["feedback"][0]["is_correct"] is True


def test_spec_and_legacy_paths_return_identical_results(ctx):
    """Both prefixes are the same blueprint - never two divergent implementations."""
    client, headers = ctx["client"], ctx["headers"]
    attempt_id = _start(ctx)

    # One response saved via the legacy path, one via the spec path.
    legacy = client.post(f"/api/v1/{attempt_id}/responses", headers=headers,
                         data=json.dumps({"question_id": ctx["q1"], "selected_keys": ["A"]}))
    spec = client.post(f"/api/v1/attempts/{attempt_id}/responses", headers=headers,
                       data=json.dumps({"question_id": ctx["q2"], "selected_keys": ["A"]}))
    assert legacy.status_code == spec.status_code == 200

    nq_legacy = client.get(f"/api/v1/{attempt_id}/next-question", headers=headers)
    nq_spec = client.get(f"/api/v1/attempts/{attempt_id}/next-question", headers=headers)
    assert nq_legacy.get_json() == nq_spec.get_json()

    client.post(f"/api/v1/attempts/{attempt_id}/submit", headers=headers)

    r_legacy = client.get(f"/api/v1/{attempt_id}/result", headers=headers)
    r_spec = client.get(f"/api/v1/attempts/{attempt_id}/result", headers=headers)
    assert r_legacy.status_code == r_spec.status_code == 200
    assert r_legacy.get_json() == r_spec.get_json()


def test_start_attempt_path_unchanged(ctx):
    """POST /api/v1/quizzes/<id>/attempts was already spec-correct; leave it."""
    assert isinstance(_start(ctx), int)


def test_spec_path_still_enforces_ownership(ctx, app):
    """The alias must not bypass the ownership check."""
    attempt_id = _start(ctx)
    with app.app_context():
        other = User(email="other@example.com", full_name="Other", password_hash="x")
        db.session.add(other)
        db.session.commit()
        other_token = create_access_token(identity=str(other.id))
    resp = ctx["client"].get(f"/api/v1/attempts/{attempt_id}/result",
                             headers={"Authorization": f"Bearer {other_token}"})
    assert resp.status_code == 403
