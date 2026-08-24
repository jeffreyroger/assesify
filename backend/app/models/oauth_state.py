"""Short-lived server-side state for the Karmayogi PKCE authorization-code flow.

Each row binds an opaque `state` value to the user who started the flow and to
the `code_verifier` that must accompany the token exchange. Rows are
single-use: `consumed` is flipped as soon as a callback is accepted so a
replayed callback cannot re-link an identity.
"""
from datetime import datetime, timedelta

from app.models.users import db

#: How long an authorization request stays valid before the user must restart.
DEFAULT_TTL_SECONDS = 600


class OAuthState(db.Model):
    __tablename__ = "oauth_states"

    id = db.Column(db.Integer, primary_key=True)
    state = db.Column(db.String(128), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    code_verifier = db.Column(db.String(256), nullable=False)
    redirect_uri = db.Column(db.String(500), nullable=False)
    provider = db.Column(db.String(50), nullable=False, default="karmayogi")
    consumed = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)

    @staticmethod
    def default_expiry(ttl_seconds: int = DEFAULT_TTL_SECONDS) -> datetime:
        return datetime.utcnow() + timedelta(seconds=ttl_seconds)

    def is_expired(self) -> bool:
        return datetime.utcnow() >= self.expires_at

    def is_usable(self) -> bool:
        return not self.consumed and not self.is_expired()

    def to_dict(self):
        return {
            "state": self.state,
            "user_id": self.user_id,
            "provider": self.provider,
            "consumed": self.consumed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat(),
        }
