from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.models.assessment import Question
from app.models.lesson import Lesson
from app.models.quiz import Quiz
from app.models.users import User

quiz_api_bp = Blueprint("quiz_api", __name__)


def _teacher_owns(teacher, quiz):
    lesson = Lesson.query.get(quiz.lesson_id)
    return bool(teacher and teacher.is_teacher and lesson and lesson.teacher_id == teacher.id)


def _legacy_items(quiz, reveal_answers):
    items = []
    for index, item in enumerate(quiz.questions or []):
        row = {"id": -(index + 1), "stem": item.get("question", ""), "qtype": "mcq",
               "options": [{"key": chr(65 + i), "text": option} for i, option in enumerate(item.get("options", []))],
               "difficulty": .5, "competency_tag": "general"}
        if reveal_answers:
            answer = item.get("correct_answer")
            row["correct_keys"] = [option["key"] for option in row["options"] if option["text"] == answer]
            row["explanation"] = item.get("answer")
        items.append(row)
    return items


@quiz_api_bp.route("", methods=["GET"])
@jwt_required()
def list_quizzes():
    user = User.query.get(int(get_jwt_identity()))
    quizzes = Quiz.query.order_by(Quiz.created_at.desc()).all()
    rows = []
    for quiz in quizzes:
        lesson = Lesson.query.get(quiz.lesson_id)
        if user.is_teacher and not _teacher_owns(user, quiz):
            continue
        rows.append({"id": quiz.id, "title": lesson.title if lesson else f"Quiz {quiz.id}",
                     "competency_tags": [lesson.topic] if lesson and lesson.topic else ["general"],
                     "question_count": Question.query.filter_by(quiz_id=quiz.id).count() or len(quiz.questions or [])})
    return jsonify({"quizzes": rows})


@quiz_api_bp.route("/<int:quiz_id>", methods=["GET"])
@jwt_required()
def get_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    user = User.query.get(int(get_jwt_identity()))
    reveal_answers = _teacher_owns(user, quiz)
    normalized = Question.query.filter_by(quiz_id=quiz.id).all()
    questions = [question.to_dict(reveal_answers=reveal_answers) for question in normalized] if normalized else _legacy_items(quiz, reveal_answers)
    lesson = Lesson.query.get(quiz.lesson_id)
    return jsonify({"id": quiz.id, "title": lesson.title if lesson else f"Quiz {quiz.id}",
                    "questions": questions, "adaptive": bool(normalized), "teacher_view": reveal_answers})
