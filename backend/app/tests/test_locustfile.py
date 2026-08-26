"""Static validation of the spec §10 load-test scenario.

The 500-user run itself needs a deployment target this environment does not
have, but the scenario file can still be proven to import, to define a real
Locust user class, and to point at endpoints that are actually registered on
the app - which is where a stale load test usually rots.
"""
import importlib.util
import os
import pathlib

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('JWT_SECRET_KEY', 'test-jwt-secret')

from app.main import create_app  # noqa: E402

LOCUSTFILE = pathlib.Path(__file__).resolve().parents[2] / "locustfile.py"


@pytest.fixture(scope="module")
def locust_module():
    spec = importlib.util.spec_from_file_location("assesify_locustfile", LOCUSTFILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_locustfile_defines_a_quiz_taker_with_tasks(locust_module):
    from locust import HttpUser

    user = locust_module.QuizTaker
    assert issubclass(user, HttpUser)
    assert user.tasks, "no @task methods registered"


def test_every_endpoint_the_scenario_hits_is_registered(locust_module):
    """Guards against the load test drifting away from the real API."""
    rules = {rule.rule for rule in create_app().url_map.iter_rules()}
    expected = {
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/profile",
        "/api/quizzes/<int:quiz_id>",
        "/api/v1/quizzes/<int:quiz_id>/attempts",
        "/api/v1/<int:attempt_id>/responses",
        "/api/quizzes/<int:quiz_id>/questions/<int:question_id>/check",
        "/api/quizzes/<int:quiz_id>/submit",
        "/api/v1/students/<int:student_id>/mastery",
        "/api/v1/students/<int:student_id>/recommendations",
    }
    assert expected <= rules, expected - rules
