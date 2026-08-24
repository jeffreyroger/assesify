"""Add normalized v1 material, question, and response records.

Revision ID: 76d4ba2e9c10
Revises: 3b7c8d4a1f02
"""
from alembic import op
import sqlalchemy as sa

revision = "76d4ba2e9c10"
down_revision = "3b7c8d4a1f02"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("materials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_materials_owner", "materials", ["owner_id"])
    op.create_table("questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("quiz_id", sa.Integer(), sa.ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stem", sa.Text(), nullable=False), sa.Column("qtype", sa.String(16), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False), sa.Column("correct_keys", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.Text()), sa.Column("difficulty", sa.Float(), nullable=False),
        sa.Column("competency_tag", sa.String(120), nullable=False),
    )
    op.create_index("ix_questions_quiz", "questions", ["quiz_id"])
    op.create_table("responses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("attempt_id", sa.Integer(), sa.ForeignKey("quiz_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("questions.id"), nullable=False),
        sa.Column("selected_keys", sa.JSON(), nullable=False), sa.Column("is_correct", sa.Boolean()),
        sa.Column("time_ms", sa.Integer()),
        sa.UniqueConstraint("attempt_id", "question_id", name="uq_response_attempt_question"),
    )
    op.create_index("ix_responses_attempt", "responses", ["attempt_id"])


def downgrade():
    op.drop_index("ix_responses_attempt", table_name="responses")
    op.drop_table("responses")
    op.drop_index("ix_questions_quiz", table_name="questions")
    op.drop_table("questions")
    op.drop_index("ix_materials_owner", table_name="materials")
    op.drop_table("materials")
