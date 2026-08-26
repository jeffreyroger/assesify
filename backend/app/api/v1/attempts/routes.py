from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.models.assessment import Question, Response
from app.models.submission import QuizAttempt
from app.models.quiz import Quiz
from app.models.users import db
from app.services.mastery_service import refresh_student_mastery
from app.models.mastery import CompetencyMastery
from ml.adaptive import select_next_question

attempts_bp = Blueprint("attempts", __name__)


def _error(code, message, status=400):
    return jsonify({"error": {"code": code, "message": message, "details": {}}}), status


@attempts_bp.route("/quizzes/<int:quiz_id>/attempts", methods=["POST"])
@jwt_required()
def start_attempt(quiz_id):
    Quiz.query.get_or_404(quiz_id)
    attempt = QuizAttempt(user_id=int(get_jwt_identity()), quiz_id=quiz_id, score=0.0,
                          completed_at=None)
    db.session.add(attempt)
    db.session.commit()
    return jsonify({"id": attempt.id, "quiz_id": quiz_id, "started_at": attempt.started_at.isoformat()}), 201


@attempts_bp.route("/<int:attempt_id>/responses", methods=["POST"])
@jwt_required()
def save_response(attempt_id):
    attempt = QuizAttempt.query.get_or_404(attempt_id)
    if attempt.user_id != int(get_jwt_identity()):
        return _error("FORBIDDEN", "You do not own this attempt.", 403)
    if attempt.completed_at:
        return _error("ATTEMPT_CLOSED", "This attempt has already been submitted.", 409)
    payload = request.get_json(silent=True) or {}
    question_id = payload.get("question_id")
    selected_keys = payload.get("selected_keys", [])
    if not question_id or not isinstance(selected_keys, list):
        return _error("VALIDATION_ERROR", "question_id and selected_keys are required.")
    question = Question.query.filter_by(id=question_id, quiz_id=attempt.quiz_id).first()
    if not question:
        return _error("VALIDATION_ERROR", "Question does not belong to this quiz.")
    response = Response.query.filter_by(attempt_id=attempt.id, question_id=question.id).first()
    if response and response.revealed_at is not None:
        # The answer key for this question has already been shown to the
        # student (via the /check feedback endpoint), so the recorded answer is
        # final - otherwise feedback would be a free retry.
        return _error("ANSWER_LOCKED",
                      "Feedback has already been given for this question; the answer is final.",
                      409)
    if not response:
        response = Response(attempt_id=attempt.id, question_id=question.id)
        db.session.add(response)
    response.selected_keys = selected_keys
    response.time_ms = payload.get("time_ms")
    response.is_correct = sorted(selected_keys) == sorted(question.correct_keys)
    db.session.commit()
    return jsonify({"question_id": question.id, "is_correct": response.is_correct}), 200


@attempts_bp.route("/<int:attempt_id>/submit", methods=["POST"])
@jwt_required()
def submit_attempt(attempt_id):
    attempt = QuizAttempt.query.get_or_404(attempt_id)
    if attempt.user_id != int(get_jwt_identity()):
        return _error("FORBIDDEN", "You do not own this attempt.", 403)
    if attempt.completed_at:
        return _error("ATTEMPT_CLOSED", "This attempt has already been submitted.", 409)
    questions = Question.query.filter_by(quiz_id=attempt.quiz_id).all()
    responses = Response.query.filter_by(attempt_id=attempt.id).all()
    if not questions:
        return _error("VALIDATION_ERROR", "This legacy quiz does not support autosaved attempts.", 422)
    answer_map = {response.question_id: response for response in responses}
    correct = sum(bool(answer_map.get(question.id) and answer_map[question.id].is_correct) for question in questions)
    attempt.score = round(100 * correct / len(questions), 2)
    attempt.completed_at = datetime.utcnow()
    db.session.commit()
    refresh_student_mastery(attempt.user_id)
    return jsonify({"attempt_id": attempt.id, "score": attempt.score, "correct": correct,
                    "total": len(questions)}), 200


@attempts_bp.route("/<int:attempt_id>/result", methods=["GET"])
@jwt_required()
def result(attempt_id):
    attempt = QuizAttempt.query.get_or_404(attempt_id)
    if attempt.user_id != int(get_jwt_identity()):
        return _error("FORBIDDEN", "You do not own this attempt.", 403)
    feedback = []
    for response in Response.query.filter_by(attempt_id=attempt.id).all():
        question = Question.query.get(response.question_id)
        feedback.append({"question": question.to_dict(reveal_answers=True), "selected_keys": response.selected_keys,
                         "is_correct": response.is_correct, "time_ms": response.time_ms})
    return jsonify({"attempt_id": attempt.id, "score": attempt.score, "submitted_at": attempt.completed_at.isoformat() if attempt.completed_at else None,
                    "feedback": feedback})


@attempts_bp.route("/<int:attempt_id>/next-question", methods=["GET"])
@jwt_required()
def next_question(attempt_id):
    attempt = QuizAttempt.query.get_or_404(attempt_id)
    if attempt.user_id != int(get_jwt_identity()):
        return _error("FORBIDDEN", "You do not own this attempt.", 403)
    answered_ids = {item.question_id for item in Response.query.filter_by(attempt_id=attempt.id).all()}
    mastery = {row.competency_tag: row.mastery for row in CompetencyMastery.query.filter_by(student_id=attempt.user_id).all()}
    question = select_next_question(Question.query.filter_by(quiz_id=attempt.quiz_id).all(), answered_ids, mastery)
    if not question:
        return jsonify({"question": None, "complete": True})
    return jsonify({"question": question.to_dict(), "complete": False})
