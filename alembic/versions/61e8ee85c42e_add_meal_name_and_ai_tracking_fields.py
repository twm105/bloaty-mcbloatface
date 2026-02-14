"""Add meal name and AI tracking fields

Revision ID: 61e8ee85c42e
Revises: 6d7c0be526eb
Create Date: 2026-01-27 22:59:14.558392

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "61e8ee85c42e"
down_revision = "6d7c0be526eb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add meal name field
    op.add_column("meals", sa.Column("name", sa.String(255), nullable=True))

    # Add AI suggested ingredients tracking (stores original AI output for evals)
    op.add_column("meals", sa.Column("ai_suggested_ingredients", JSONB, nullable=True))

    # Add source tracking to meal_ingredients (ai vs manual)
    op.add_column(
        "meal_ingredients",
        sa.Column("source", sa.String(20), nullable=True, server_default="manual"),
    )


def downgrade() -> None:
    # Remove added columns
    op.drop_column("meal_ingredients", "source")
    op.drop_column("meals", "ai_suggested_ingredients")
    op.drop_column("meals", "name")
