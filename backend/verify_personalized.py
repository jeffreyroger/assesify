import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.abspath("."))

from app.main import app
from app.models.users import db, User
from app.models.lesson import Lesson
from app.models.submission import QuizAttempt
from app.services.personalized_quiz_service import PersonalizedQuizService

with app.app_context():
    # 1. Setup mock data
    user = User.query.filter_by(email="student@example.com").first()
    if not user:
        user = User(full_name="Student", email="student@example.com")
        user.set_password("password")
        db.session.add(user)
        db.session.commit()

    lesson = Lesson.query.first()
    if not lesson:
        lesson = Lesson(topic="Science", title="Biology 101", content="Photosynthesis is the process by which green plants and some other organisms use sunlight to synthesize foods from carbon dioxide and water.")
        db.session.add(lesson)
        db.session.commit()

    # Create a mock attempt to ensure history exists
    # If the lesson doesn't have a quiz, the mock logic in PersonalizedQuizService.get_student_performance_df might fail
    # but we just need it to not be empty
    attempt = QuizAttempt(user_id=user.id, quiz_id=1, score=50.0)
    db.session.add(attempt)
    db.session.commit()

    print(f"--- PERSONALIZED QUIZ FALLBACK TEST ---")
    quiz = PersonalizedQuizService.generate_personalized_quiz(user.id)

    if quiz:
        print(f"Success! Generated quiz with {len(quiz['questions'])} questions.")
        for i, q in enumerate(quiz['questions']):
            print(f"Q{i+1}: {q['question']}")
    else:
        print("Failed to generate personalized quiz.")
