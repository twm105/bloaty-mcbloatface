"""add_auth_tables

Revision ID: 3b4c5d6e7f8g
Revises: 2a3b4c5d6e7f
Create Date: 2026-02-08

Adds:
- password_hash and is_admin fields to users table
- sessions table for user login sessions
- invites table for invite-only registration

Note: After running this migration, create an admin user with:
    docker-compose exec web python -m app.cli create-admin --email your@email.com
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '3b4c5d6e7f8g'
down_revision = '2a3b4c5d6e7f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add auth fields to users table
    op.add_column('users', sa.Column('password_hash', sa.String(255), nullable=True))
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), nullable=True, server_default='false'))

    # Set default for existing rows and make non-nullable
    op.execute("UPDATE users SET is_admin = false WHERE is_admin IS NULL")
    op.alter_column('users', 'is_admin', nullable=False, server_default='false')

    # Create sessions table
    op.create_table(
        'sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('user_agent', sa.String(512), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sessions_token'), 'sessions', ['token'], unique=True)
    op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'], unique=False)
    op.create_index(op.f('ix_sessions_expires_at'), 'sessions', ['expires_at'], unique=False)

    # Create invites table
    op.create_table(
        'invites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(64), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('used_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['used_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_invites_token'), 'invites', ['token'], unique=True)
    op.create_index(op.f('ix_invites_created_by'), 'invites', ['created_by'], unique=False)
    op.create_index(op.f('ix_invites_expires_at'), 'invites', ['expires_at'], unique=False)


def downgrade() -> None:
    # Drop invites table
    op.drop_index(op.f('ix_invites_expires_at'), table_name='invites')
    op.drop_index(op.f('ix_invites_created_by'), table_name='invites')
    op.drop_index(op.f('ix_invites_token'), table_name='invites')
    op.drop_table('invites')

    # Drop sessions table
    op.drop_index(op.f('ix_sessions_expires_at'), table_name='sessions')
    op.drop_index(op.f('ix_sessions_user_id'), table_name='sessions')
    op.drop_index(op.f('ix_sessions_token'), table_name='sessions')
    op.drop_table('sessions')

    # Remove auth fields from users table
    op.drop_column('users', 'is_admin')
    op.drop_column('users', 'password_hash')
