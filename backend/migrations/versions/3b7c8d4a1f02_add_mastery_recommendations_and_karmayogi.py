"""Add competency snapshots, recommendations, and Karmayogi identity link.

Revision ID: 3b7c8d4a1f02
Revises: f5c8d1966aa6
"""
from alembic import op
import sqlalchemy as sa


revision = "3b7c8d4a1f02"
down_revision = "f5c8d1966aa6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("karmayogi_user_id", sa.String(length=255), nullable=True))
    op.create_table(
        "competency_mastery",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("competency_tag", sa.String(length=120), nullable=False),
        sa.Column("mastery", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "competency_tag", name="uq_mastery_student_competency"),
    )
    op.create_index("ix_competency_mastery_student", "competency_mastery", ["student_id"])
    op.create_table(
        "recommendations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("competency_tag", sa.String(length=120), nullable=False),
        sa.Column("karmayogi_course_id", sa.String(length=255), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("course_title", sa.String(length=255), nullable=True),
        sa.Column("course_url", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("recommendations")
    op.drop_index("ix_competency_mastery_student", table_name="competency_mastery")
    op.drop_table("competency_mastery")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("karmayogi_user_id")
