from app.models.users import db
from datetime import datetime

class Quiz(db.Model):
    __tablename__ = 'quizzes'

    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lessons.id'), nullable=False)
    questions = db.Column(db.JSON, nullable=False)  # Stores the list of questions/answers
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def question_count(self):
        """Number of questions on this quiz.

        Prefers relational `Question` rows; falls back to the deprecated
        `questions` JSON blob for quizzes that predate the relational schema.
        """
        from app.models.assessment import Question

        count = Question.query.filter_by(quiz_id=self.id).count()
        return count or (len(self.questions) if self.questions else 0)

    def to_dict(self, include_answers=False):
        # Prefer relational Question rows (the spec-compliant path) when they
        # exist, converting them back into the legacy generator-dict shape so
        # existing frontend consumers of this JSON blob don't need to change.
        # The `questions` JSON column is kept only as a deprecated fallback
        # for quizzes that predate the relational Question rows.
        #
        # `include_answers` defaults to False: the sanitized (student) view of
        # spec §4.3 carries no `correct_answer`/`answer`. Callers that have
        # established the caller is the owning teacher pass True.
        from app.models.assessment import Question
        from app.services.quiz_generation import legacy_shape_from_questions, redact_legacy_blob

        related = Question.query.filter_by(quiz_id=self.id).order_by(Question.id).all()
        if related:
            questions_data = legacy_shape_from_questions(related, include_answers=include_answers)
        else:
            blob = self.questions or []
            questions_data = blob if include_answers else redact_legacy_blob(blob)

        return {
            "id": self.id,
            "lesson_id": self.lesson_id,
            "questions": questions_data,
            "created_at": self.created_at.isoformat()
        }
