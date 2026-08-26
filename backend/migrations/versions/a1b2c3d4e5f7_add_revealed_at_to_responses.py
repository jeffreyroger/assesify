"""add revealed_at to responses

Revision ID: a1b2c3d4e5f7
Revises: f6a7b8c9d0e1
Create Date: 2026-08-26

Binds answer-key reveal to a recorded response: once feedback has been served
for a response it is locked against overwriting.
"""
import sqlalchemy as sa
from alembic import op

revision = 'a1b2c3d4e5f7'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('responses') as batch_op:
        batch_op.add_column(sa.Column('revealed_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('responses') as batch_op:
        batch_op.drop_column('revealed_at')
