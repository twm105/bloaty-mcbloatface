"""add_discounted_ingredients

Revision ID: 4c5d6e7f8g9h
Revises: 3b4c5d6e7f8g
Create Date: 2026-02-11

Adds:
- discounted_ingredients table for storing confounded ingredients that were
  analyzed but discarded during diagnosis. Preserves full analysis context.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "4c5d6e7f8g9h"
down_revision = "3b4c5d6e7f8g"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discounted_ingredients",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("diagnosis_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "ingredient_id",
            sa.Integer(),
            sa.ForeignKey("ingredients.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # Discard justification
        sa.Column("discard_justification", sa.Text(), nullable=False),
        sa.Column(
            "confounded_by_ingredient_id",
            sa.Integer(),
            sa.ForeignKey("ingredients.id"),
            nullable=True,
        ),
        # Original correlation data
        sa.Column("original_confidence_score", sa.Numeric(5, 3), nullable=True),
        sa.Column("original_confidence_level", sa.String(), nullable=True),
        sa.Column("times_eaten", sa.Integer(), nullable=True),
        sa.Column("times_followed_by_symptoms", sa.Integer(), nullable=True),
        sa.Column("immediate_correlation", sa.Integer(), nullable=True),
        sa.Column("delayed_correlation", sa.Integer(), nullable=True),
        sa.Column("cumulative_correlation", sa.Integer(), nullable=True),
        sa.Column("associated_symptoms", postgresql.JSONB(), nullable=True),
        # Co-occurrence data
        sa.Column("conditional_probability", sa.Numeric(4, 3), nullable=True),
        sa.Column("reverse_probability", sa.Numeric(4, 3), nullable=True),
        sa.Column("lift", sa.Numeric(5, 2), nullable=True),
        sa.Column("cooccurrence_meals_count", sa.Integer(), nullable=True),
        # Medical grounding
        sa.Column("medical_grounding_summary", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("discounted_ingredients")
