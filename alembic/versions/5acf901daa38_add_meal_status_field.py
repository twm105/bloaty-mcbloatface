"""Add meal status field

Revision ID: 5acf901daa38
Revises: 61e8ee85c42e
Create Date: 2026-01-27 23:33:16.285248

"""
from alembic import op
import sqlalchemy as sa


revision = '5acf901daa38'
down_revision = '61e8ee85c42e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add status field: 'draft' or 'published'
    # Default to 'published' for existing meals, new meals will be 'draft'
    op.add_column('meals', sa.Column('status', sa.String(20), nullable=False, server_default='published'))


def downgrade() -> None:
    op.drop_column('meals', 'status')
