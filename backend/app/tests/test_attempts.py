import os
import json
from datetime import datetime

import pytest

# Ensure we use an in-memory sqlite DB for tests
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('JWT_SECRET_KEY', 'test-jwt-secret')

from app.main import create_app
from app.models.users import db, User
from app.models.lesson import Lesson
from app.models.quiz import Quiz
from app.models.assessment import Question
from app.models.submission import QuizAttempt
from flask_jwt_extended import create_access_token


@pytest.fixture
def app():
    app = create_app()
    # create tables
    with app.app_context():
        db.create_all()
    yield app


def test_attempt_lifecycle(app):
    client = app.test_client()

    # create user and resources
    with app.app_context():
        user = User(email='student@example.com', full_name='Student', password_hash='fakehash')
        db.session.add(user)
        db.session.commit()

        lesson = Lesson(title='Test Lesson', content='Content', topic='Test')
        db.session.add(lesson)
        db.session.commit()

        quiz = Quiz(lesson_id=lesson.id, questions=[])
        db.session.add(quiz)
        db.session.commit()

        # add two questions for the quiz
        q1 = Question(quiz_id=quiz.id, stem='What is 2+2?', options=['3','4','5'], correct_keys=['B'], explanation='2+2=4')
        q2 = Question(quiz_id=quiz.id, stem='What is capital of FR?', options=['Paris','Berlin'], correct_keys=['A'], explanation='Paris')
        db.session.add_all([q1, q2])
        db.session.commit()

        # create access token
        token = create_access_token(identity=str(user.id))

        # capture IDs while still attached to session
        quiz_id = quiz.id
        q1_id = q1.id
        q2_id = q2.id

    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

    # Start an attempt
    resp = client.post(f'/api/v1/quizzes/{quiz_id}/attempts', headers=headers)
    print('START ATTEMPT RESP', resp.status_code, resp.get_data(as_text=True))
    assert resp.status_code == 201
    body = resp.get_json()
    attempt_id = body['id']

    # Save a response for question 1 (incorrect)
    payload = {'question_id': q1_id, 'selected_keys': ['A']}
    resp = client.post(f'/api/v1/{attempt_id}/responses', headers=headers, data=json.dumps(payload))
    assert resp.status_code == 200
    j = resp.get_json()
    assert j['is_correct'] is False

    # Save response for question 2 (correct)
    payload = {'question_id': q2.id, 'selected_keys': ['A']}
    resp = client.post(f'/api/v1/{attempt_id}/responses', headers=headers, data=json.dumps(payload))
    assert resp.status_code == 200
    j = resp.get_json()
    assert j['is_correct'] is True

    # Submit attempt
    resp = client.post(f'/api/v1/{attempt_id}/submit', headers=headers)
    assert resp.status_code == 200
    j = resp.get_json()
    assert j['total'] == 2
    assert j['correct'] == 1
    assert 'score' in j
