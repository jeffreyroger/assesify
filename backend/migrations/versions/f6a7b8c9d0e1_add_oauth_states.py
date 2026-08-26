"""add oauth_states table for the Karmayogi PKCE flow

Revision ID: f6a7b8c9d0e1
Revises: b2c3d4e5f6a7
Create Date: 2026-08-24 21:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6a7b8c9d0e1'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'oauth_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('state', sa.String(length=128), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('code_verifier', sa.String(length=256), nullable=False),
        sa.Column('redirect_uri', sa.String(length=500), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False, server_default='karmayogi'),
        # NOTE: must be sa.false(), not sa.text('0'). PostgreSQL rejects an
        # integer DEFAULT on a boolean column ("default expression is of type
        # integer"), which made this migration fail on Postgres while working
        # fine on SQLite. sa.false() renders correctly on both dialects.
        sa.Column('consumed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_oauth_states_user_id_users'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('state', name='uq_oauth_states_state'),
    )
    op.create_index(op.f('ix_oauth_states_state'), 'oauth_states', ['state'], unique=False)
    op.create_index(op.f('ix_oauth_states_user_id'), 'oauth_states', ['user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_oauth_states_user_id'), table_name='oauth_states')
    op.drop_index(op.f('ix_oauth_states_state'), table_name='oauth_states')
    op.drop_table('oauth_states')
