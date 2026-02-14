"""Add meal local_timezone column

Revision ID: 6e7f8g9h0i1j
Revises: 5d6e7f8g9h0i
Create Date: 2026-02-14

Adds local_timezone column to meals table for timezone-aware day grouping.
Users may travel, so each meal stores the timezone it was logged in.
"""

from alembic import op
import sqlalchemy as sa


revision = "6e7f8g9h0i1j"
down_revision = "5d6e7f8g9h0i"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add local_timezone column - nullable since existing meals won't have it
    # Existing meals will be treated as UTC when grouping by day
    op.add_column("meals", sa.Column("local_timezone", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("meals", "local_timezone")
