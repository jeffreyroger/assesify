"""Competency-mastery estimator used by the API.

Implements a simple 1PL / Rasch-style estimator per competency: for each
competency c, fit a scalar ability theta_c using item difficulties b_i and
binary responses y_i where

    P(y_i=1) = sigmoid(theta_c - b_i).

Theta is fit via Newton-Raphson with L2 regularization; mastery is sigmoid(theta).

The function still supports legacy attempt-score aggregation as a fallback when
item-level responses are not available.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Iterable, List

from app.models.lesson import Lesson
from app.models.mastery import CompetencyMastery
from app.models.quiz import Quiz
from app.models.submission import QuizAttempt
from app.models.users import db
from ml.integrations.karmayogi.sync import push_mastery_event

# Import pure functions implemented in a small independent module for testability
from app.services.irt import fit_theta_rasch, _sigmoid


GAP_THRESHOLD = 0.60

    """Fit a single theta (ability) parameter for the Rasch 1PL model.

    difficulties: iterable of item difficulties (expected ~0..1) — these are
    rescaled internally to logit-like offsets. outcomes: iterable of 0/1.
    Returns theta (real number). Regularization 'reg' applies an L2 penalty
    (reg * theta^2).
    """
    import math

    b = [float(x) for x in difficulties]
    y = [1 if int(v) else 0 for v in outcomes]
    n = len(b)
    if n == 0:
        return 0.0

    # Map difficulties in [0,1] to a prior scale centered near 0.
    # A simple transform: b' = (difficulty - 0.5) * 4 -> roughly [-2,2]
    b_scaled = [(val - 0.5) * 4.0 for val in b]

    # initial theta: use logit(mean(y)) + mean(b_scaled)
    mean_y = sum(y) / n
    eps = 1e-3
    if mean_y <= 0:
        theta = -1.0 + sum(b_scaled) / n
    elif mean_y >= 1:
        theta = 1.0 + sum(b_scaled) / n
    else:
        theta = _logit(mean_y) + sum(b_scaled) / n

    # Newton-Raphson
    for _ in range(max_iter):
        ps = [_sigmoid(theta - bi) for bi in b_scaled]
        # gradient: sum(y - p) - 2*reg*theta
        grad = sum(yi - pi for yi, pi in zip(y, ps)) - 2.0 * reg * theta
        # Hessian (second derivative): -sum(p*(1-p)) - 2*reg
        hess = -sum(pi * (1.0 - pi) for pi in ps) - 2.0 * reg
        if hess == 0:
            break
        delta = grad / hess
        theta_new = theta - delta
        if abs(theta_new - theta) < tol:
            theta = theta_new
            break
        theta = theta_new
    return float(theta)


def refresh_student_mastery(student_id: int):
    """Refresh per-competency mastery estimates for a student.

    Uses item-level responses (Response + Question) when present; otherwise
    falls back to aggregating legacy QuizAttempt scores per lesson topic.
    """
    cutoff = datetime.utcnow() - timedelta(days=90)

    # Try to use item-level responses first
    from app.models.assessment import Question, Response
    from app.models.submission import QuizAttempt

    # Query responses joined to attempts/questions
    rows = []

    # Map: competency_tag -> list of (difficulty, outcome)
    samples = defaultdict(list)

    responses = (
        db.session.query(Response, Question, QuizAttempt)
        .join(Question, Response.question_id == Question.id)
        .join(QuizAttempt, Response.attempt_id == QuizAttempt.id)
        .filter(QuizAttempt.user_id == student_id, QuizAttempt.completed_at >= cutoff)
        .all()
    )

    for resp, question, attempt in responses:
        tag = (question.competency_tag or "general").strip().lower()
        outcome = 1 if resp.is_correct else 0
        difficulty = float(getattr(question, "difficulty", 0.5) or 0.5)
        samples[tag].append((difficulty, outcome))

    # If no item-level responses found, fall back to legacy attempt-scores grouped by lesson topic
    if not samples:
        attempts = QuizAttempt.query.filter(
            QuizAttempt.user_id == student_id,
            QuizAttempt.completed_at >= cutoff,
        ).all()
        for attempt in attempts:
            quiz = Quiz.query.get(attempt.quiz_id)
            lesson = Lesson.query.get(quiz.lesson_id) if quiz else None
            tag = (lesson.topic if lesson and lesson.topic else "general").strip().lower()
            samples[tag].append((0.5, max(0.0, min(1.0, attempt.score / 100.0))))

    # Fit theta per competency and persist
    for tag, items in samples.items():
        difficulties, outcomes = zip(*items) if items else ([], [])
        try:
            theta = fit_theta_rasch(difficulties, outcomes, reg=1.0)
            mastery = _sigmoid(theta)
        except Exception:
            # fallback to simple average with prior
            vals = [o for _, o in items]
            mastery = (sum(vals) + 0.5) / (len(vals) + 1) if vals else 0.5

        row = CompetencyMastery.query.filter_by(student_id=student_id, competency_tag=tag).first()
        if not row:
            row = CompetencyMastery(student_id=student_id, competency_tag=tag)
            db.session.add(row)
        row.mastery = float(max(0.0, min(1.0, mastery)))
        rows.append(row)

    db.session.commit()

    # Sync is best effort so an unavailable external service never blocks scoring.
    from app.models.users import User
    user = User.query.get(student_id)
    if user and user.karmayogi_user_id:
        for row in rows:
            push_mastery_event(user.karmayogi_user_id, row.competency_tag, row.mastery)
    return rows


def gaps_for_student(student_id: int):
    refresh_student_mastery(student_id)
    rows = CompetencyMastery.query.filter_by(student_id=student_id).all()
    gaps = [
        {
            "competency_tag": row.competency_tag,
            "mastery": round(float(row.mastery), 3),
            "gap_score": round(GAP_THRESHOLD - float(row.mastery), 3),
        }
        for row in rows if row.mastery < GAP_THRESHOLD
    ]
    return sorted(gaps, key=lambda gap: gap["gap_score"], reverse=True)
