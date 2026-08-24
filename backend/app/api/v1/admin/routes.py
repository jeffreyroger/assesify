from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app.core.authz import require_role
from app.models.audit_log import AuditLog
from app.models.users import User

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/audit-log", methods=["GET"])
@jwt_required()
@require_role("admin")
def list_audit_log():
    """Paginated list of audit_log entries, newest first (admin-only)."""
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("per_page", 20, type=int)))
    query = AuditLog.query.order_by(AuditLog.created_at.desc())
    total = query.count()
    entries = query.offset((page - 1) * per_page).limit(per_page).all()
    return jsonify({
        "entries": [entry.to_dict() for entry in entries],
        "page": page,
        "per_page": per_page,
        "total": total,
    })


@admin_bp.route("/users/<int:user_id>", methods=["GET"])
@jwt_required()
@require_role("admin")
def view_user(user_id):
    """Admin lookup of another user's account details.

    Viewing another user's data is a sensitive action, so it is logged to
    audit_log separately from the generic per-route logging done by
    `require_role('admin')`, with the specific target user recorded.
    """
    user = User.query.get_or_404(user_id)
    from flask_jwt_extended import get_jwt_identity

    from app.services.audit_service import log_admin_action
    log_admin_action(
        actor_id=int(get_jwt_identity()),
        action="admin_view_user",
        target_type="user",
        target_id=user.id,
    )
    return jsonify(user.to_dict())
