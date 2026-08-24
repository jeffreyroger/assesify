"""Helper for recording admin actions to the audit_log table (spec §8)."""
import json

from app.models.audit_log import AuditLog
from app.models.users import db


def log_admin_action(actor_id, action, target_type=None, target_id=None, details=None):
    """Insert an audit_log row for an admin action.

    `details` may be a plain string or a JSON-serializable object (dict/list),
    which will be serialized to a string before storage.
    """
    if details is not None and not isinstance(details, str):
        try:
            details = json.dumps(details)
        except TypeError:
            details = str(details)
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details=details,
    )
    db.session.add(entry)
    db.session.commit()
    return entry
