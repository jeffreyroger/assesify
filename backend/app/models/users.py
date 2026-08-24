from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_teacher = db.Column(db.Boolean, default=False)
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
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
