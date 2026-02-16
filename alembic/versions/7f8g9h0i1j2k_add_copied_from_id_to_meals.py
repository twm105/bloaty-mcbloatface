"""Add copied_from_id to meals for duplicate tracking

Revision ID: 7f8g9h0i1j2k
Revises: 6e7f8g9h0i1j
Create Date: 2026-02-16

Adds copied_from_id column to track meal duplication lineage.
When a meal is duplicated, the copy references the original meal.
"""

from alembic import op
import sqlalchemy as sa


revision = "7f8g9h0i1j2k"
down_revision = "6e7f8g9h0i1j"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add copied_from_id column with self-referential foreign key
    op.add_column(
        "meals",
        sa.Column(
            "copied_from_id",
            sa.Integer(),
            sa.ForeignKey("meals.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("idx_meals_copied_from_id", "meals", ["copied_from_id"])


def downgrade() -> None:
    op.drop_index("idx_meals_copied_from_id", "meals")
    op.drop_column("meals", "copied_from_id")
