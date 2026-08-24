from app.models.users import db
from datetime import datetime

class QuizAttempt(db.Model):
    __tablename__ = 'quiz_attempts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quizzes.id'), nullable=False)
    # If the user took this quiz as part of a specific class context:
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=True)
    
    score = db.Column(db.Float, nullable=False, default=0.0) # e.g. 85.0
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    user = db.relationship('User', backref='quiz_attempts')
    quiz = db.relationship('Quiz', backref='attempts')
    # class_ rel if needed
    
    # Store detailed answers
    answers = db.relationship('QuizAnswer', backref='attempt', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "quiz_id": self.quiz_id,
            "class_id": self.class_id,
            "score": self.score,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "answers": [a.to_dict() for a in self.answers]
        }

class QuizAnswer(db.Model):
    __tablename__ = 'quiz_answers'

    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey('quiz_attempts.id'), nullable=False)
    
    # Identify the question. Since questions are JSON in Quiz, we might use index or question text hash.
    # Using simple index or question text for now.
    question_text = db.Column(db.Text, nullable=False)
    student_answer_text = db.Column(db.Text, nullable=True)
    is_correct = db.Column(db.Boolean, default=False)

    def to_dict(self):
        return {
            "question_text": self.question_text,
            "student_answer": self.student_answer_text,
            "is_correct": self.is_correct
        }
