from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.models.mastery import Recommendation
from app.models.users import User, db
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
        for rec in recommend_for_gap(gap["competency_tag"]):
            rec.setdefault("competency_tag", gap["competency_tag"])
            recommendations.append(rec)
    _persist_recommendations(student_id, recommendations)
    return jsonify({"recommendations": recommendations})


def _persist_recommendations(student_id, recommendations):
    """Upsert computed recommendations into the `recommendations` table (spec §3.1)."""
    for rec in recommendations:
        competency_tag = rec.get("competency_tag") or rec.get("competency") or ""
        course_id = rec.get("course_id")
        row = Recommendation.query.filter_by(
            student_id=student_id,
            competency_tag=competency_tag,
            karmayogi_course_id=course_id,
        ).first()
        if row is None:
            row = Recommendation(
                student_id=student_id,
                competency_tag=competency_tag,
                karmayogi_course_id=course_id,
            )
            db.session.add(row)
        row.score = float(rec.get("score", 0.5) or 0.5)
        row.reason = rec.get("reason", "")
        row.course_title = rec.get("title")
        row.course_url = rec.get("url")
    db.session.commit()
