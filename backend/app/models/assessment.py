"""Normalized assessment records used by the versioned API.

Legacy quizzes retain their JSON payload for backwards compatibility.  These
models provide the item-level records needed for autosave, feedback, mastery,
and adaptive selection.
"""
from datetime import datetime

from app.models.users import db


class Material(db.Model):
    __tablename__ = "materials"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    mime_type = db.Column(db.String(120), nullable=False)
    extracted_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self, include_text=False):
        data = {"id": self.id, "title": self.title, "mime_type": self.mime_type,
                "created_at": self.created_at.isoformat()}
        if include_text:
            data["extracted_text"] = self.extracted_text
        return data


class Question(db.Model):
    __tablename__ = "questions"

    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True)
    stem = db.Column(db.Text, nullable=False)
    qtype = db.Column(db.String(16), nullable=False, default="mcq")
    options = db.Column(db.JSON, nullable=False, default=list)
    correct_keys = db.Column(db.JSON, nullable=False, default=list)
    explanation = db.Column(db.Text, nullable=True)
    difficulty = db.Column(db.Float, nullable=False, default=0.5)
    competency_tag = db.Column(db.String(120), nullable=False, default="general")

    def to_dict(self, reveal_answers=False):
        data = {"id": self.id, "stem": self.stem, "qtype": self.qtype,
                "options": self.options, "difficulty": self.difficulty,
                "competency_tag": self.competency_tag}
        if reveal_answers:
            data.update({"correct_keys": self.correct_keys, "explanation": self.explanation})
        return data


class Response(db.Model):
    __tablename__ = "responses"

    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("quiz_attempts.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    selected_keys = db.Column(db.JSON, nullable=False, default=list)
    is_correct = db.Column(db.Boolean, nullable=True)
    time_ms = db.Column(db.Integer, nullable=True)

    __table_args__ = (db.UniqueConstraint("attempt_id", "question_id", name="uq_response_attempt_question"),)
