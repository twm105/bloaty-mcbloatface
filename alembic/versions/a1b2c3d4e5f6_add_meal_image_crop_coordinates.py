"""Add meal image crop coordinates

Revision ID: a1b2c3d4e5f6
Revises: 5acf901daa38
Create Date: 2026-01-31 13:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "5acf901daa38"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add crop coordinate columns for circular image cropping
    # Defaults to 50.0 (center of image)
    op.add_column(
        "meals",
        sa.Column(
            "meal_image_crop_x", sa.Float(), nullable=True, server_default="50.0"
        ),
    )
    op.add_column(
        "meals",
        sa.Column(
            "meal_image_crop_y", sa.Float(), nullable=True, server_default="50.0"
        ),
    )


def downgrade() -> None:
    op.drop_column("meals", "meal_image_crop_y")
    op.drop_column("meals", "meal_image_crop_x")
