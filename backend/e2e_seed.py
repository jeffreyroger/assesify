"""Seed a disposable database for the Playwright E2E suite (spec §10).

Creates the schema, a teacher who owns a lesson, and one quiz with relational
`Question` rows - the same shape `app/services/quiz_generation.py` produces for
a real material upload, so the quiz-taking flow under test is the real one.

Never point this at `assesify_dev.db`: it is meant to run against a throwaway
`DATABASE_URL` (see `frontend/playwright.config.ts`). Prints the seeded quiz id
as JSON on stdout so the E2E setup can pick it up.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import create_app  # noqa: E402
from app.models.lesson import Lesson  # noqa: E402
from app.models.quiz import Quiz  # noqa: E402
from app.models.users import User, db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.services.quiz_generation import persist_quiz_questions  # noqa: E402

QUESTIONS = [
    {"question": "What is 2 + 2?", "options": ["3", "4", "5", "6"],
     "correct_answer": "4", "answer": "Basic arithmetic.", "hint": "Count on your fingers."},
    {"question": "What is the capital of France?",
     "options": ["Paris", "Berlin", "Madrid", "Rome"],
     "correct_answer": "Paris", "answer": "Paris has been the capital since the 10th century.",
     "hint": "Think Eiffel Tower."},
]

TEACHER_EMAIL = "e2e.teacher@example.com"
TEACHER_PASSWORD = "E2eTeacherPass123!"


def main():
    app = create_app()
    with app.app_context():
        db.create_all()

        teacher = User.find_by_email(TEACHER_EMAIL)
        if teacher is None:
            teacher = User(email=TEACHER_EMAIL, full_name="E2E Teacher",
                           password_hash=hash_password(TEACHER_PASSWORD), is_teacher=True)
            db.session.add(teacher)
            db.session.flush()

        lesson = Lesson(title="E2E Fundamentals", content="2+2=4. The capital of France is Paris.",
                        topic="general", teacher_id=teacher.id)
        db.session.add(lesson)
        db.session.flush()

        quiz = Quiz(lesson_id=lesson.id, questions=[])
        db.session.add(quiz)
        db.session.flush()
        persist_quiz_questions(quiz.id, QUESTIONS, competency_tag="general")
        db.session.commit()

        print(json.dumps({"quiz_id": quiz.id, "lesson_id": lesson.id,
                          "teacher_email": TEACHER_EMAIL,
                          "teacher_password": TEACHER_PASSWORD}))


if __name__ == "__main__":
    main()
