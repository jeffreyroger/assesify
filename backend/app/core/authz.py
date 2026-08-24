from functools import wraps
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from flask import jsonify, request
from app.models.users import User


def get_current_user():
    """Return the current user or None if not authenticated."""
    try:
        verify_jwt_in_request(optional=True)
        uid = get_jwt_identity()
        if not uid:
            return None
        return User.query.get(int(uid))
    except Exception:
        return None


def require_role(role: str):
    """Decorator to require a role ('teacher' or 'admin').

    Returns 403 JSON when not allowed.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({"error": {"code": "FORBIDDEN", "message": "Authentication required", "details": {}}}), 403
            if role == 'teacher' and not user.is_teacher:
                return jsonify({"error": {"code": "FORBIDDEN", "message": "Teacher role required", "details": {}}}), 403
            if role == 'admin' and not getattr(user, 'is_admin', False):
                return jsonify({"error": {"code": "FORBIDDEN", "message": "Admin role required", "details": {}}}), 403
            if role == 'admin':
                # Every admin-guarded route gets an audit_log entry automatically
                # (spec §8: "audit log for admin access").
                try:
                    from app.services.audit_service import log_admin_action
                    log_admin_action(
                        actor_id=user.id,
                        action=fn.__name__,
                        target_type="route",
                        target_id=request.path,
                        details={"method": request.method, "kwargs": kwargs},
                    )
                except Exception:
                    # Never let audit logging break the actual admin action.
                    pass
            return fn(*args, **kwargs)
        return wrapper
    return decorator
