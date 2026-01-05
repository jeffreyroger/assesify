import sys
import os

# Add backend folder to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import app
from app.models.users import db, User
from app.models.lesson import Lesson
from app.models.quiz import Quiz as QuizModel
from app.models.submission import QuizAttempt, QuizAnswer
from app.services.personalized_quiz_service import PersonalizedQuizService
from datetime import datetime

def test_personalization():
    with app.app_context():
        # 1. Setup a test student
        test_email = "ml_test_student@example.com"
        user = User.query.filter_by(email=test_email).first()
        if not user:
            user = User(
                email=test_email,
                full_name="ML Test Student",
                password_hash="...",
                is_teacher=False
            )
            db.session.add(user)
            db.session.commit()
            print(f"Created test user: {user.id}")

        # 2. Setup a lesson
        lesson = Lesson.query.filter_by(topic="Biology").first()
        if not lesson:
            lesson = Lesson(
                title="Biology Basics",
                topic="Biology",
                content="Cells are the basic unit of life. DNA is the blueprint."
            )
            db.session.add(lesson)
            db.session.commit()
            print(f"Created test lesson: {lesson.id}")

        # 3. Create a quiz for that lesson
        quiz = QuizModel.query.filter_by(lesson_id=lesson.id).first()
        if not quiz:
            quiz = QuizModel(
                lesson_id=lesson.id,
                questions=[{"question": "What is a cell?", "options": ["A", "B", "C", "D"], "correct_answer": "A"}]
            )
            db.session.add(quiz)
            db.session.commit()

        # 4. Create some "failure" history for the student
        # Simulate 2 failing attempts (20% score)
        for i in range(2):
            attempt = QuizAttempt(
                user_id=user.id,
                quiz_id=quiz.id,
                score=20.0,
                completed_at=datetime.utcnow()
            )
            db.session.add(attempt)
        db.session.commit()
        print(f"Created 'weak' history for user {user.id} in topic {lesson.topic}")

        # 5. Try to generate a personalized quiz
        print("\n--- Generating Personalized Quiz ---")
        personalized_quiz = PersonalizedQuizService.generate_personalized_quiz(user.id)
        
        if personalized_quiz:
            print("Success!")
            print(f"Quiz ID: {personalized_quiz['id']}")
            print(f"Questions Generated: {len(personalized_quiz['questions'])}")
            for idx, q in enumerate(personalized_quiz['questions']):
                print(f"\nQ{idx+1}: {q['question']}")
                print(f"Options: {q.get('options') or q.get('choices')}")
                print(f"Correct: {q.get('correct_answer')}")
                print(f"Hint/Expl: {q.get('hint') or q.get('explanation')}")
        else:
            print("Failed to generate personalized quiz.")

if __name__ == "__main__":
    # Ensure GEMINI_API_KEY is set if possible, otherwise it might fail or use mock (if implemented)
    # Since I don't have the key, I'll see what the current GeminiClient does
    test_personalization()
