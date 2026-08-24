from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from app.core.security import hash_password, verify_password
from app.core.encrypted_type import EncryptedString, compute_lookup_hash

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    # `email` is encrypted at rest (spec §8 PII-at-rest requirement); ciphertext
    # is longer than the plaintext, so the column is sized generously. All
    # lookups/uniqueness checks go through `email_lookup_hash` instead, since
    # encryption is non-deterministic and can't be used in a WHERE clause.
    email = db.Column(EncryptedString(500), nullable=False)
    email_lookup_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    full_name = db.Column(EncryptedString(500), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_teacher = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    major = db.Column(db.String(100), nullable=True)
    location = db.Column(db.String(100), nullable=True)
    
    # Gamification fields
    streak = db.Column(db.Integer, default=0)
    diamonds = db.Column(db.Integer, default=0)
    health = db.Column(db.Integer, default=5)
    profile_pic = db.Column(db.String(255), nullable=True)
    karmayogi_user_id = db.Column(db.String(255), nullable=True)
    last_active_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "is_teacher": self.is_teacher,
            "is_admin": self.is_admin,
            "major": self.major,
            "location": self.location,
            "profile_pic": self.profile_pic,
            "karmayogi_user_id": self.karmayogi_user_id,
            "streak": self.streak,
            "diamonds": self.diamonds,
            "health": self.health,
            "last_active_date": self.last_active_date.isoformat() if self.last_active_date else None,
            "created_at": self.created_at.isoformat()
        }

    def set_password(self, password):
        self.password_hash = hash_password(password)

    def check_password(self, password):
        return verify_password(password, self.password_hash)

    def set_email(self, email: str):
        """Set both the encrypted email and its deterministic lookup hash.

        Always use this instead of assigning `.email` directly, so the two
        stay in sync (a stale/missing hash would make the user un-findable
        by login/uniqueness checks).
        """
        self.email = email
        self.email_lookup_hash = compute_lookup_hash(email)

    @staticmethod
    def find_by_email(email: str):
        """Look up a user by email via the deterministic hash column
        (the encrypted `email` column itself can't be used in a WHERE clause).
        """
        return User.query.filter_by(email_lookup_hash=compute_lookup_hash(email)).first()


from sqlalchemy import event


@event.listens_for(User, "before_insert")
@event.listens_for(User, "before_update")
def _sync_email_lookup_hash(mapper, connection, target):
    """Keep `email_lookup_hash` in sync even if code sets `.email` directly
    instead of calling `set_email()` (e.g. `User(email=...)` constructor).

    Runs before the encrypting TypeDecorator's bind param processing, so
    `target.email` here is still the plaintext value assigned by the caller.
    """
    if target.email is not None:
        target.email_lookup_hash = compute_lookup_hash(target.email)
