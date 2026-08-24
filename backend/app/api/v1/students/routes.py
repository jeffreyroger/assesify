from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.models.users import User
from app.services.karmayogi_service import recommend_for_gap
from app.services.mastery_service import gaps_for_student, refresh_student_mastery

students_bp = Blueprint("students", __name__)


def _can_access(student_id: int):
    requester = User.query.get(int(get_jwt_identity()))
    return requester and (requester.id == student_id or requester.is_teacher)


@students_bp.route("/<int:student_id>/mastery", methods=["GET"])
@jwt_required()
def mastery(student_id):
    if not _can_access(student_id):
        return jsonify({"error": {"code": "FORBIDDEN", "message": "Not allowed to view this learner."}}), 403
    return jsonify({"mastery": [row.to_dict() for row in refresh_student_mastery(student_id)]})


@students_bp.route("/<int:student_id>/gaps", methods=["GET"])
@jwt_required()
def gaps(student_id):
    if not _can_access(student_id):
        return jsonify({"error": {"code": "FORBIDDEN", "message": "Not allowed to view this learner."}}), 403
    return jsonify({"gaps": gaps_for_student(student_id), "threshold": 0.6})


@students_bp.route("/<int:student_id>/recommendations", methods=["GET"])
@jwt_required()
def recommendations(student_id):
    if not _can_access(student_id):
        return jsonify({"error": {"code": "FORBIDDEN", "message": "Not allowed to view this learner."}}), 403
    recommendations = []
    for gap in gaps_for_student(student_id):
        recommendations.extend(recommend_for_gap(gap["competency_tag"]))
    return jsonify({"recommendations": recommendations})
