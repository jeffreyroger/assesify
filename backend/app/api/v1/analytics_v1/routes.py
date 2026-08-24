from collections import defaultdict

from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.models.assessment import Question, Response
from app.models.classes import Class
from app.models.submission import QuizAttempt
from app.models.users import User

analytics_v1_bp = Blueprint("analytics_v1", __name__)


@analytics_v1_bp.route("/teachers/cohorts/<int:class_id>/analytics", methods=["GET"])
@jwt_required()
def cohort_analytics(class_id):
    teacher = User.query.get(int(get_jwt_identity()))
    cohort = Class.query.get_or_404(class_id)
    if not teacher or not teacher.is_teacher or cohort.teacher_id != teacher.id:
        return jsonify({"error": {"code": "FORBIDDEN", "message": "Only the cohort teacher can view analytics.", "details": {}}}), 403
    attempts = QuizAttempt.query.filter_by(class_id=class_id).all()
    scores = [attempt.score for attempt in attempts if attempt.completed_at]
    incorrect = defaultdict(int)
    totals = defaultdict(int)
    for response in Response.query.join(QuizAttempt).filter(QuizAttempt.class_id == class_id).all():
        totals[response.question_id] += 1
        if not response.is_correct:
            incorrect[response.question_id] += 1
    items = []
    for question_id, total in totals.items():
        question = Question.query.get(question_id)
        items.append({"question_id": question_id, "stem": question.stem if question else "Question",
                      "competency_tag": question.competency_tag if question else "general",
                      "incorrect_rate": round(incorrect[question_id] / total, 3)})
    return jsonify({"class_id": class_id, "attempt_count": len(scores),
                    "average_score": round(sum(scores) / len(scores), 2) if scores else None,
                    "item_analysis": sorted(items, key=lambda item: item["incorrect_rate"], reverse=True)})
