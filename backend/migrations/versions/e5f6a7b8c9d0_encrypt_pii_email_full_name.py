"""encrypt PII: email/full_name at rest + email_lookup_hash

Spec §8 calls for pgcrypto encryption of `email`/`full_name`. This repo runs
on SQLite (no pgcrypto), so encryption is done at the application layer via
`app.core.encrypted_type.EncryptedString` (Fernet). This migration:
  1. Widens `email`/`full_name` to hold ciphertext (longer than plaintext).
  2. Adds an indexed, unique `email_lookup_hash` column (deterministic
     HMAC-SHA256 of the normalized email) used for all login/uniqueness
     lookups, since ciphertext can't be matched with a plain `WHERE email = ?`.
  3. Backfills existing rows: encrypts existing plaintext `email`/`full_name`
     values in place and computes their lookup hash.

Revision ID: e5f6a7b8c9d0
Revises: d3e4f5a6b7c8
Create Date: 2026-08-24 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd3e4f5a6b7c8'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Widen columns to fit ciphertext, add the lookup-hash column (nullable
    #    for now so the backfill below can populate it row-by-row).
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('email', existing_type=sa.String(length=120), type_=sa.String(length=500))
        batch_op.alter_column('full_name', existing_type=sa.String(length=100), type_=sa.String(length=500))
        batch_op.add_column(sa.Column('email_lookup_hash', sa.String(length=64), nullable=True))

    # 2. Backfill: encrypt existing plaintext email/full_name and compute the
    #    deterministic lookup hash, using the same helpers the app uses so
    #    values are readable by the app afterwards.
    from app.core.encrypted_type import _get_fernet, compute_lookup_hash

    connection = op.get_bind()
    users = connection.execute(sa.text('SELECT id, email, full_name FROM users')).fetchall()
    fernet = _get_fernet()
    for row in users:
        user_id, email, full_name = row[0], row[1], row[2]
        if email is None:
            continue
        encrypted_email = fernet.encrypt(str(email).encode('utf-8')).decode('utf-8')
        lookup_hash = compute_lookup_hash(email)
        encrypted_name = (
            fernet.encrypt(str(full_name).encode('utf-8')).decode('utf-8')
            if full_name is not None else None
        )
        connection.execute(
            sa.text(
                'UPDATE users SET email = :email, full_name = :full_name, '
                'email_lookup_hash = :hash WHERE id = :id'
            ),
            {'email': encrypted_email, 'full_name': encrypted_name, 'hash': lookup_hash, 'id': user_id},
        )

    # 3. Now that every row has a hash, enforce NOT NULL + unique index.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('email_lookup_hash', existing_type=sa.String(length=64), nullable=False)
        batch_op.create_index(batch_op.f('ix_users_email_lookup_hash'), ['email_lookup_hash'], unique=True)


def downgrade():
    # Best-effort: decrypt values back to plaintext before dropping the hash
    # column and shrinking the columns back down.
    from app.core.encrypted_type import _get_fernet

    connection = op.get_bind()
    users = connection.execute(sa.text('SELECT id, email, full_name FROM users')).fetchall()
    fernet = _get_fernet()
    for row in users:
        user_id, email, full_name = row[0], row[1], row[2]
        try:
            decrypted_email = fernet.decrypt(email.encode('utf-8')).decode('utf-8') if email else email
        except Exception:
            decrypted_email = email
        try:
            decrypted_name = fernet.decrypt(full_name.encode('utf-8')).decode('utf-8') if full_name else full_name
        except Exception:
            decrypted_name = full_name
        connection.execute(
            sa.text('UPDATE users SET email = :email, full_name = :full_name WHERE id = :id'),
            {'email': decrypted_email, 'full_name': decrypted_name, 'id': user_id},
        )

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_email_lookup_hash'))
        batch_op.drop_column('email_lookup_hash')
        batch_op.alter_column('full_name', existing_type=sa.String(length=500), type_=sa.String(length=100))
        batch_op.alter_column('email', existing_type=sa.String(length=500), type_=sa.String(length=120))
