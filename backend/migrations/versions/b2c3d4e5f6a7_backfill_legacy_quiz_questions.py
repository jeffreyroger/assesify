"""backfill legacy Quiz.questions JSON blob into relational Question rows

Every write path (`/teacher/materials`, `/lessons/:id/quiz`,
`/materials/:id/generate-quiz`) now persists relational `Question` rows
instead of the legacy `quizzes.questions` JSON blob column. This migration
is a one-time data backfill: for any existing quiz that has rows in
`questions` in its JSON blob but no matching relational `Question` rows
(i.e. it was created before this change), we materialize `Question` rows
from the blob so reads/attempts/scoring/mastery are consistent for old data
too. The `quizzes.questions` column itself is intentionally NOT dropped —
kept as a deprecated, unused-on-write fallback (see TEST_STATUS.md).

Revision ID: b2c3d4e5f6a7
Revises: c34d7f13f504
Create Date: 2026-08-24 23:30:00.000000

"""
import json

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'c34d7f13f504'
branch_labels = None
depends_on = None

DIFFICULTY_SCORES = {"easy": 0.3, "medium": 0.5, "hard": 0.8}


def _rows_from_blob(quiz_id, items):
    rows = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        options = item.get("options") or []
        correct = item.get("correct_answer")
        option_rows = [{"key": chr(65 + i), "text": value} for i, value in enumerate(options)]
        correct_keys = [row["key"] for row in option_rows if row["text"] == correct]
        if not correct_keys and option_rows:
            correct_keys = ["A"]
        rows.append({
            "quiz_id": quiz_id,
            "stem": item.get("question") or "",
            "qtype": "mcq",
            "options": json.dumps(option_rows),
            "correct_keys": json.dumps(correct_keys),
            "explanation": item.get("answer"),
            "difficulty": DIFFICULTY_SCORES.get("medium", 0.5),
            "competency_tag": "general",
        })
    return rows


def upgrade():
    bind = op.get_bind()

    quiz_rows = bind.execute(sa.text("SELECT id, questions FROM quizzes")).fetchall()
    if not quiz_rows:
        return

    existing_quiz_ids = {
        row[0]
        for row in bind.execute(sa.text("SELECT DISTINCT quiz_id FROM questions")).fetchall()
    }

    insert_stmt = sa.text(
        "INSERT INTO questions (quiz_id, stem, qtype, options, correct_keys, explanation, difficulty, competency_tag) "
        "VALUES (:quiz_id, :stem, :qtype, :options, :correct_keys, :explanation, :difficulty, :competency_tag)"
    )

    for quiz_id, questions_blob in quiz_rows:
        if quiz_id in existing_quiz_ids:
            continue  # already has relational rows, nothing to backfill
        if not questions_blob:
            continue
        items = questions_blob if isinstance(questions_blob, list) else json.loads(questions_blob)
        rows = _rows_from_blob(quiz_id, items)
        for row in rows:
            bind.execute(insert_stmt, row)


def downgrade():
    # Backfilled rows are indistinguishable from natively-created relational
    # rows once inserted, so there is no safe automated way to remove only
    # the backfilled ones. This is a data-only, additive migration; no-op.
    pass
