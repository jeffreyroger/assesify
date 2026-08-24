"""
Test script for Weekly Personalized Test System

This script simulates a student taking multiple quizzes throughout a week,
then generates a personalized weekly test based on their performance.
"""
import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.main import app
from app.models.users import db, User
from app.models.lesson import Lesson
from app.models.quiz import Quiz
from app.models.submission import QuizAttempt
from app.services.personalized_quiz_service import PersonalizedQuizService
from werkzeug.security import generate_password_hash

def setup_test_data():
    """Create test user and quiz attempts for the week."""
    with app.app_context():
        # Create or get test user
        test_user = User.find_by_email('weekly_test@example.com')
        if not test_user:
            test_user = User(
                email='weekly_test@example.com',
                full_name='Weekly Test Student',
                password_hash=generate_password_hash('password123'),
                is_teacher=False
            )
            db.session.add(test_user)
            db.session.flush()
        
        print(f"✓ Test user created: ID {test_user.id}")
        
        # Get or create lessons for different topics
        topics_data = [
            ('Biology', 'Cell Structure', 'Content about cells...'),
            ('Biology', 'Photosynthesis', 'Content about photosynthesis...'),
            ('Mathematics', 'Algebra Basics', 'Content about algebra...'),
            ('Physics', 'Newton\'s Laws', 'Content about Newton\'s laws...'),
        ]
        
        lessons = []
        for topic, title, content in topics_data:
            lesson = Lesson.query.filter_by(topic=topic, title=title).first()
            if not lesson:
                lesson = Lesson(topic=topic, title=title, content=content)
                db.session.add(lesson)
                db.session.flush()
            lessons.append(lesson)
        
        print(f"✓ Created {len(lessons)} lessons")
        
        # Create quizzes for each lesson
        quizzes = []
        for lesson in lessons:
            quiz = Quiz.query.filter_by(lesson_id=lesson.id).first()
            if not quiz:
                quiz = Quiz(
                    lesson_id=lesson.id,
                    questions=[
                        {
                            "question": f"Sample question 1 for {lesson.title}?",
                            "options": ["A", "B", "C", "D"],
                            "correct_answer": "A",
                            "answer": "Explanation",
                            "hint": "Hint"
                        },
                        {
                            "question": f"Sample question 2 for {lesson.title}?",
                            "options": ["A", "B", "C", "D"],
                            "correct_answer": "B",
                            "answer": "Explanation",
                            "hint": "Hint"
                        }
                    ]
                )
                db.session.add(quiz)
                db.session.flush()
            quizzes.append(quiz)
        
        print(f"✓ Created {len(quizzes)} quizzes")
        
        # Create quiz attempts with varying performance
        # Biology: weak (20% and 40%)
        # Math: medium (60%)
        # Physics: strong (90%)
        
        attempts_data = [
            (quizzes[0].id, 20.0, 3),  # Biology Cell - weak, 3 days ago
            (quizzes[1].id, 40.0, 2),  # Biology Photo - weak, 2 days ago
            (quizzes[2].id, 60.0, 1),  # Math - medium, 1 day ago
            (quizzes[3].id, 90.0, 0),  # Physics - strong, today
        ]
        
        for quiz_id, score, days_ago in attempts_data:
            completed_at = datetime.utcnow() - timedelta(days=days_ago)
            attempt = QuizAttempt(
                user_id=test_user.id,
                quiz_id=quiz_id,
                score=score,
                started_at=completed_at,
                completed_at=completed_at
            )
            db.session.add(attempt)
        
        db.session.commit()
        print(f"✓ Created {len(attempts_data)} quiz attempts with varying performance")
        
        return test_user.id

def test_weekly_performance(user_id):
    """Test the weekly performance aggregation."""
    with app.app_context():
        print("\n--- Testing Weekly Performance Aggregation ---")
        
        # Get current week dates
        now = datetime.utcnow()
        start_of_week = now - timedelta(days=now.weekday())
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)
        
        performance = PersonalizedQuizService.get_weekly_performance(
            user_id, start_of_week, end_of_week
        )
        
        print(f"\nWeek: {start_of_week.date()} to {end_of_week.date()}")
        print(f"Topics covered: {len(performance['topics'])}")
        
        for topic in performance['topics']:
            print(f"\n  Topic: {topic['topic']}")
            print(f"    Accuracy: {topic['accuracy']}%")
            print(f"    Attempts: {topic['total_attempts']}")
            print(f"    Weight: {topic['weight']} (higher = more questions needed)")
        
        return performance

def test_weekly_test_generation(user_id):
    """Test the weekly test generation."""
    with app.app_context():
        print("\n--- Generating Weekly Test ---")
        
        # Get current week dates
        now = datetime.utcnow()
        start_of_week = now - timedelta(days=now.weekday())
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)
        
        try:
            quiz_data = PersonalizedQuizService.generate_weekly_test(
                user_id, 
                num_questions=8,  # Generate 8 questions
                start_date=start_of_week,
                end_date=end_of_week
            )
            
            if quiz_data:
                print(f"\n✓ Weekly test generated successfully!")
                print(f"  Quiz ID: {quiz_data['id']}")
                print(f"  Total Questions: {len(quiz_data['questions'])}")
                print(f"  Topic Distribution: {quiz_data.get('topic_distribution', {})}")
                
                # Show sample questions
                print(f"\n  Sample Questions:")
                for i, q in enumerate(quiz_data['questions'][:3], 1):
                    print(f"    {i}. [{q.get('topic', 'N/A')}] {q['question'][:60]}...")
                
                return quiz_data
            else:
                print("✗ Failed to generate weekly test")
                return None
        except Exception as e:
            print(f"✗ Error generating weekly test: {e}")
            import traceback
            traceback.print_exc()
            return None

if __name__ == '__main__':
    print("=" * 60)
    print("Weekly Personalized Test System - Verification")
    print("=" * 60)
    
    # Setup test data
    user_id = setup_test_data()
    
    # Test weekly performance
    performance = test_weekly_performance(user_id)
    
    # Test weekly test generation
    quiz = test_weekly_test_generation(user_id)
    
    print("\n" + "=" * 60)
    if quiz:
        print("✓ All tests passed!")
        print("\nExpected behavior:")
        print("  - Biology should have the most questions (weakest topic)")
        print("  - Physics should have the fewest questions (strongest topic)")
        print("  - Math should be in the middle")
    else:
        print("✗ Some tests failed. Check the output above.")
    print("=" * 60)
