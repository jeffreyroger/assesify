from datetime import datetime

from app.models.users import db


class CompetencyMastery(db.Model):
    """Persisted, per-learner estimate for a competency (0.0 through 1.0)."""

    __tablename__ = "competency_mastery"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    competency_tag = db.Column(db.String(120), nullable=False)
    mastery = db.Column(db.Float, nullable=False, default=0.5)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("student_id", "competency_tag", name="uq_mastery_student_competency"),)

    def to_dict(self):
        return {
            "competency_tag": self.competency_tag,
            "mastery": round(float(self.mastery), 3),
            "updated_at": self.updated_at.isoformat(),
        }


class Recommendation(db.Model):
    """A recommended Karmayogi course or an internal remedial quiz."""

    __tablename__ = "recommendations"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    competency_tag = db.Column(db.String(120), nullable=False)
    karmayogi_course_id = db.Column(db.String(255), nullable=True)
    score = db.Column(db.Float, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    course_title = db.Column(db.String(255), nullable=True)
    course_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            "competency_tag": self.competency_tag,
            "course_id": self.karmayogi_course_id,
            "title": self.course_title,
            "url": self.course_url,
            "score": round(float(self.score), 3),
            "reason": self.reason,
            "source": "karmayogi" if self.karmayogi_course_id else "internal",
        }
