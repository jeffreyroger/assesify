from flask import Blueprint, jsonify, request
from datetime import datetime
from app.models.users import db, User
from app.models.quiz import Quiz
from app.models.submission import QuizAttempt, QuizAnswer
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.models.assessment import Question
from app.services.personalized_quiz_service import PersonalizedQuizService
from app.services.mastery_service import refresh_student_mastery

quizzes_bp = Blueprint('quizzes', __name__)

@quizzes_bp.route('/generate-personalized', methods=['POST'])
@jwt_required()
def generate_personalized_quiz():
    """Generate a personalized quiz for the authenticated user.

    This endpoint no longer accepts caller-supplied user_id; use the
    authenticated identity to determine the target student. This prevents
    spoofing other users' IDs.
    """
    data = request.get_json() or {}
    topic_filter = data.get('topic')

    auth_user = int(get_jwt_identity())

    quiz_data = PersonalizedQuizService.generate_personalized_quiz(auth_user, topic_filter)

    if not quiz_data:
        return jsonify({"error": "Failed to generate personalized quiz"}), 500

    return jsonify(quiz_data), 200


@quizzes_bp.route('/weekly-performance', methods=['GET'])
@jwt_required()
def get_weekly_performance():
    """Get authenticated student's performance aggregated for a specific week."""
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if not start_date_str or not end_date_str:
        return jsonify({"error": "start_date and end_date are required"}), 400

    try:
        start_date = datetime.fromisoformat(start_date_str)
        end_date = datetime.fromisoformat(end_date_str)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use ISO format (YYYY-MM-DD)"}), 400

    auth_user = int(get_jwt_identity())
    performance = PersonalizedQuizService.get_weekly_performance(auth_user, start_date, end_date)
    return jsonify(performance), 200


@quizzes_bp.route('/generate-weekly-test', methods=['POST'])
@jwt_required()
def generate_weekly_test():
    """Generate a personalized weekly test for the authenticated student."""
    data = request.get_json() or {}
    num_questions = data.get('num_questions', 10)  # Default to 10 questions
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')

    if not start_date_str or not end_date_str:
        return jsonify({"error": "start_date and end_date are required"}), 400

    try:
        start_date = datetime.fromisoformat(start_date_str)
        end_date = datetime.fromisoformat(end_date_str)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use ISO format (YYYY-MM-DD)"}), 400

    auth_user = int(get_jwt_identity())
    quiz_data = PersonalizedQuizService.generate_weekly_test(auth_user, num_questions, start_date, end_date)

    if not quiz_data:
        return jsonify({"error": "Failed to generate weekly test"}), 500

    return jsonify(quiz_data), 201

@quizzes_bp.route('/<int:quiz_id>', methods=['GET'])
def get_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    return jsonify(quiz.to_dict())

@quizzes_bp.route('/recent', methods=['GET'])
def get_recent_quizzes():
    # Return last 5 quizzes
    quizzes = Quiz.query.order_by(Quiz.created_at.desc()).limit(5).all()
    results = []
    for q in quizzes:
        # Get lesson title
        from app.models.lesson import Lesson
        lesson = Lesson.query.get(q.lesson_id)
        question_count = Question.query.filter_by(quiz_id=q.id).count() or (len(q.questions) if q.questions else 0)
        results.append({
            "id": q.id,
            "title": lesson.title if lesson else f"Quiz {q.id}",
            "topic": lesson.topic if lesson else "General",
            "questions_count": question_count,
            "created_at": q.created_at.isoformat()
        })
    return jsonify(results)

def _grade_against_question(question, answer_payload):
    """Score one submitted answer server-side against its stored `Question` row.

    Accepts either `selected_keys` (option keys, e.g. `["B"]`) or, failing
    that, `answer` (the option's literal text, which is mapped back to a key).
    Returns True only when the selected keys match the question's
    `correct_keys` exactly.
    """
    correct_keys = sorted(str(key) for key in (question.correct_keys or []))
    selected = answer_payload.get('selected_keys')
    if selected is None:
        text = answer_payload.get('answer')
        selected = [opt.get('key') for opt in (question.options or []) if opt.get('text') == text]
    if isinstance(selected, str):
        selected = [selected]
    selected = sorted(str(key) for key in (selected or []))
    return bool(selected) and selected == correct_keys


@quizzes_bp.route('/<int:quiz_id>/submit', methods=['POST'])
@jwt_required()
def submit_quiz(quiz_id):
    data = request.get_json() or {}
    # Expect: { "class_id": optional, "answers": [{ "question": "...", "answer": "...", "is_correct": true }] }
    # Additionally supported (preferred): each answer may carry "question_id"
    # (and optionally "selected_keys"), in which case correctness is determined
    # server-side from the relational `Question` row rather than trusting the
    # client-supplied "is_correct". The legacy shape above still works.
    
    quiz = Quiz.query.get_or_404(quiz_id)
    
    # Use authenticated identity to avoid caller-supplied user_id
    from flask_jwt_extended import get_jwt_identity
    auth_user_id = int(get_jwt_identity())
    user = User.query.get(auth_user_id)

    class_id = data.get('class_id')
    answers_data = data.get('answers', [])

    if user and user.is_teacher:
        # Teacher: Do not save attempt (teacher preview)
        return jsonify({
            "message": "Quiz completed (Teacher Mode - Not Saved)",
            "score": 100.0 # simple placeholder
        }), 200

    # Grade every answer first: server-authoritative when the client identified
    # the question by id, otherwise falling back to the legacy client-supplied
    # `is_correct` flag so existing clients keep working unchanged.
    graded = []
    for ans in answers_data:
        question = None
        question_id = ans.get('question_id')
        if question_id is not None:
            question = Question.query.filter_by(id=question_id, quiz_id=quiz.id).first()
        if question is not None:
            graded.append({
                'question_text': question.stem,
                'student_answer': ans.get('answer'),
                'is_correct': _grade_against_question(question, ans),
            })
        else:
            graded.append({
                'question_text': ans.get('question'),
                'student_answer': ans.get('answer'),
                'is_correct': bool(ans.get('is_correct', False)),
            })

    # Calculate score
    total_q = len(graded)
    correct_c = sum(1 for g in graded if g['is_correct'])
    score = (correct_c / total_q * 100) if total_q > 0 else 0.0

    attempt = QuizAttempt(
        user_id=auth_user_id,
        quiz_id=quiz.id,
        class_id=class_id,
        score=score
    )
    
    db.session.add(attempt)
    db.session.flush() # get ID

    for entry in graded:
        is_correct = entry['is_correct']
        q_ans = QuizAnswer(
            attempt_id=attempt.id,
            question_text=entry['question_text'],
            student_answer_text=entry['student_answer'],
            is_correct=is_correct
        )
        db.session.add(q_ans)
        
        # Gamification: Decrease health on wrong answer
        if not is_correct and user:
            user.health = max(0, user.health - 1)

    # Gamification: Streak logic
    diamonds_earned = 0
    if user:
        from datetime import date, timedelta
        today = date.today()
        if user.last_active_date is None:
            user.streak = 1
        elif user.last_active_date == today:
            pass # already active today
        elif user.last_active_date == today - timedelta(days=1):
            user.streak += 1
        else:
            # Missed at least one day
            user.streak = 1 # starting new streak 
        
        user.last_active_date = today
        
        # Gamification: Diamonds (simple logic: +5 per correct answer)
        diamonds_earned = correct_c * 5
        user.diamonds += diamonds_earned

    db.session.commit()
    refresh_student_mastery(auth_user_id)
    
    return jsonify({
        "message": "Quiz submitted successfully",
        "attempt_id": attempt.id,
        "score": score,
        "health": user.health if user else 5,
        "streak": user.streak if user else 0,
        "diamonds_earned": diamonds_earned
    }), 201
