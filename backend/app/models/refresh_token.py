from datetime import datetime
from app.models.users import db


class RefreshToken(db.Model):
    __tablename__ = "refresh_tokens"
    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(64), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    revoked = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)

    def revoke(self):
        self.revoked = True

    def is_expired(self):
        return datetime.utcnow() >= self.expires_at

    def to_dict(self):
        return {
            "id": self.id,
            "jti": self.jti,
            "user_id": self.user_id,
            "revoked": self.revoked,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat()
        }
