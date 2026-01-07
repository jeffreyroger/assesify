from typing import List, Optional, Dict, Any
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
from app.models.users import db, User
from app.models.submission import QuizAttempt, QuizAnswer
from app.models.lesson import Lesson
from app.models.quiz import Quiz as QuizModel
from ml.recommender import advanced_aggregate, recommend_actions, generate_quiz_from_action
from ml.genai import GeminiClient

class PersonalizedQuizService:
    @staticmethod
    def get_student_performance_df(user_id: int) -> pd.DataFrame:
        """Fetch all quiz attempts for a student and format for ML recommender."""
        attempts = QuizAttempt.query.filter_by(user_id=user_id).all()
        data = []
        for att in attempts:
            quiz = QuizModel.query.get(att.quiz_id)
            if not quiz or not quiz.lesson_id:
                continue
            
            lesson = Lesson.query.get(quiz.lesson_id)
            if not lesson:
                continue

            # Calculate metrics for this attempt
            # Accuracy is score / 100
            accuracy = att.score / 100.0
            
            # Placeholder for avg_time_per_question if not tracked
            # We'll use a default of 30 seconds per question for now
            avg_time = 30.0 
            
            data.append({
                "student_id": str(user_id),
                "topic": lesson.topic or "General",
                "subtopic": lesson.title, # Using title as subtopic for granularity
                "accuracy": accuracy,
                "avg_time_per_question": avg_time,
                "attempt_date": att.completed_at or att.started_at,
                "difficulty": "medium" # Defaulting for historical data, though models could track this
            })
        
        return pd.DataFrame(data)

    @staticmethod
    def generate_personalized_quiz(user_id: int, topic_filter: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Orchestrate personalized quiz generation for a student."""
        df = PersonalizedQuizService.get_student_performance_df(user_id)
        
        if df.empty:
            # Fallback: Generate a general quiz from a lesson if no history exists
            if topic_filter:
                lesson = Lesson.query.filter(Lesson.topic.ilike(f"%{topic_filter}%")).first()
            
            if not lesson:
                lesson = Lesson.query.first()
                
            if not lesson:
                return None
            
            from ml.train.quiz_gen import generate_quiz
            questions = generate_quiz(lesson.content, difficulty="medium", num_questions=5)
            
            new_quiz = QuizModel(
                lesson_id=lesson.id,
                questions=questions
            )
            db.session.add(new_quiz)
            db.session.commit()
            return new_quiz.to_dict()

        # 1. Aggregate data
        agg_df = advanced_aggregate(df)
        
        # 2. Get recommendations
        actions = recommend_actions(agg_df, str(user_id))
        if not actions:
            return None
        
        # Filter by topic if requested
        action = actions[0]
        if topic_filter:
            filtered = [a for a in actions if a.topic.lower() == topic_filter.lower()]
            if filtered:
                action = filtered[0]

        # 3. Generate quiz using Gemini
        try:
            client = GeminiClient()
            quiz_json = generate_quiz_from_action(client, action, n_questions=5)
            
            # The recommender prompt returns {'quiz': [...]}
            questions = quiz_json.get('quiz', [])
            
            # Map 'choices' to 'options' if needed (schemas might differ slightly)
            for q in questions:
                if 'choices' in q and 'options' not in q:
                    q['options'] = q.pop('choices')
        except Exception as e:
            print(f"Personalized AI generation failed, using Smart Fallback. Error: {e}")
            # Fallback to standard smart generation using the lesson content
            lesson = Lesson.query.filter(Lesson.topic == action.topic).first()
            if lesson:
                from ml.train.quiz_gen import generate_quiz
                questions = generate_quiz(lesson.content, difficulty=action.recommended_difficulty, num_questions=5)
            else:
                return None

        # Create and return the quiz
        if questions:
            # Re-fetch lesson just in case
            lesson = Lesson.query.filter(Lesson.topic == action.topic).first()
            new_quiz = QuizModel(
                lesson_id=lesson.id if lesson else None,
                questions=questions
            )
            db.session.add(new_quiz)
            db.session.commit()
            return new_quiz.to_dict()
        
        return None

    @staticmethod
    def get_weekly_performance(user_id: int, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Aggregate student performance for a specific week.
        
        Returns:
            {
                'topics': [
                    {
                        'topic': str,
                        'subtopic': str,
                        'accuracy': float,
                        'avg_time': float,
                        'mistake_count': int,
                        'total_attempts': int,
                        'weight': float
                    }
                ]
            }
        """
        # Fetch all quiz attempts in the date range
        attempts = QuizAttempt.query.filter(
            QuizAttempt.user_id == user_id,
            QuizAttempt.completed_at >= start_date,
            QuizAttempt.completed_at <= end_date
        ).all()
        
        if not attempts:
            return {'topics': []}
        
        # Group by topic
        topic_data = defaultdict(lambda: {
            'total_score': 0,
            'total_attempts': 0,
            'total_time': 0,
            'mistake_count': 0,
            'subtopics': set()
        })
        
        for att in attempts:
            quiz = QuizModel.query.get(att.quiz_id)
            if not quiz or not quiz.lesson_id:
                continue
            
            lesson = Lesson.query.get(quiz.lesson_id)
            if not lesson:
                continue
            
            topic = lesson.topic or "General"
            
            # Aggregate metrics
            topic_data[topic]['total_score'] += att.score
            topic_data[topic]['total_attempts'] += 1
            topic_data[topic]['subtopics'].add(lesson.title)
            
            # Count mistakes (100 - score gives percentage wrong)
            topic_data[topic]['mistake_count'] += (100 - att.score) / 10  # Rough estimate
            
            # Estimate time (placeholder - would need actual time tracking)
            topic_data[topic]['total_time'] += 30 * len(quiz.questions)  # 30s per question
        
        # Calculate weights and format response
        topics = []
        for topic, data in topic_data.items():
            accuracy = data['total_score'] / (data['total_attempts'] * 100)
            avg_time = data['total_time'] / data['total_attempts']
            max_time = 60 * len(quiz.questions) if quiz else 300  # Max expected time
            
            # Calculate weight based on performance
            # More weight = more questions needed
            weight = (
                (1 - accuracy) * 0.5 +  # 50% weight on low accuracy
                min(avg_time / max_time, 1.0) * 0.3 +  # 30% weight on time
                min(data['mistake_count'] / data['total_attempts'], 1.0) * 0.2  # 20% weight on mistakes
            )
            
            topics.append({
                'topic': topic,
                'subtopic': ', '.join(list(data['subtopics'])[:3]),  # First 3 subtopics
                'accuracy': round(accuracy * 100, 2),
                'avg_time': round(avg_time, 2),
                'mistake_count': int(data['mistake_count']),
                'total_attempts': data['total_attempts'],
                'weight': round(weight, 3)
            })
        
        # Sort by weight (highest first - weakest topics)
        topics.sort(key=lambda x: x['weight'], reverse=True)
        
        return {'topics': topics}
    
    @staticmethod
    def calculate_question_distribution(topics: List[Dict], total_questions: int) -> Dict[str, int]:
        """Calculate how many questions each topic should get based on weights."""
        if not topics:
            return {}
        
        total_weight = sum(t['weight'] for t in topics)
        if total_weight == 0:
            # Equal distribution if all weights are 0
            questions_per_topic = total_questions // len(topics)
            return {t['topic']: questions_per_topic for t in topics}
        
        distribution = {}
        remaining_questions = total_questions
        
        for i, topic in enumerate(topics):
            if i == len(topics) - 1:
                # Last topic gets remaining questions
                distribution[topic['topic']] = remaining_questions
            else:
                # Proportional distribution
                num_questions = int((topic['weight'] / total_weight) * total_questions)
                num_questions = max(1, num_questions)  # At least 1 question per topic
                distribution[topic['topic']] = num_questions
                remaining_questions -= num_questions
        
        return distribution
    
    @staticmethod
    def generate_weekly_test(user_id: int, num_questions: int, start_date: datetime, end_date: datetime) -> Optional[Dict[str, Any]]:
        """Generate a personalized weekly test based on student's performance.
        
        Args:
            user_id: Student ID
            num_questions: Total number of questions to generate
            start_date: Start of the week
            end_date: End of the week
            
        Returns:
            Quiz dict with weighted questions from weak topics
        """
        # Get weekly performance
        performance = PersonalizedQuizService.get_weekly_performance(user_id, start_date, end_date)
        topics = performance.get('topics', [])
        
        if not topics:
            # No activity this week - generate a general quiz
            lesson = Lesson.query.first()
            if not lesson:
                return None
            
            from ml.train.quiz_gen import generate_quiz
            questions = generate_quiz(lesson.content)
            
            new_quiz = QuizModel(
                lesson_id=lesson.id,
                questions=questions
            )
            db.session.add(new_quiz)
            db.session.commit()
            return new_quiz.to_dict()
        
        # Calculate question distribution
        distribution = PersonalizedQuizService.calculate_question_distribution(topics, num_questions)
        
        # Generate questions for each topic
        all_questions = []
        client = GeminiClient()
        
        for topic_name, question_count in distribution.items():
            if question_count == 0:
                continue
            
            # Find topic data
            topic_data = next((t for t in topics if t['topic'] == topic_name), None)
            if not topic_data:
                continue
            
            # Create a refined prompt for this topic
            prompt = f"""You are an elite educational assessment expert. Generate {question_count} high-fidelity, professional multiple-choice questions for: {topic_name}.

**Topic Context**: {topic_data['subtopic']}
**Target Mastery**: {topic_data['accuracy']}% (Personalize for improvement)

**ASSESSMENT STANDARDS**:
1. **100% Standalone**: Every question must be self-contained. NO references to "the passage" or external texts.
2. **Concept-Focus**: Test principles and application, not text verbatim.
3. **Elite Tone**: Use professional, clear, assessments-oriented language.
4. **Distractors**: 4 distinct, plausible options. 

**JSON Format**:
{{
  "quiz": [
    {{
      "question": "Question text?",
      "options": ["A", "B", "C", "D"],
      "correct_answer": "A",
      "answer": "Explanation of correct concept.",
      "hint": "Clue for thinking."
    }}
  ]
}}
"""
            
            try:
                quiz_json = client.generate_json(prompt)
                questions = quiz_json.get('quiz', [])
                
                # Add topic metadata to each question
                for q in questions:
                    q['topic'] = topic_name
                    if 'choices' in q and 'options' not in q:
                        q['options'] = q.pop('choices')
                
                all_questions.extend(questions[:question_count])
            except Exception as e:
                print(f"AI generation failed for topic {topic_name}, using Smart Fallback. Error: {e}")
                # Fallback to smart keyword-based generation
                lesson = Lesson.query.filter(Lesson.topic == topic_name).first()
                if lesson:
                    from ml.train.quiz_gen import generate_quiz
                    fallback_qs = generate_quiz(lesson.content, num_questions=question_count)
                    for q in fallback_qs:
                        q['topic'] = topic_name
                    all_questions.extend(fallback_qs)
                continue
        
        if not all_questions:
            return None
        
        # Create the weekly test quiz
        # Use the first topic's lesson as the parent (or create a special weekly test lesson)
        first_topic = topics[0]['topic']
        lesson = Lesson.query.filter(Lesson.topic == first_topic).first()
        
        new_quiz = QuizModel(
            lesson_id=lesson.id if lesson else None,
            questions=all_questions
        )
        db.session.add(new_quiz)
        db.session.commit()
        
        # Return with metadata
        result = new_quiz.to_dict()
        result['is_weekly_test'] = True
        result['topic_distribution'] = distribution
        result['week_start'] = start_date.isoformat()
        result['week_end'] = end_date.isoformat()
        
        return result
