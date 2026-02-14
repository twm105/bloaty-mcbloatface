"""Seed initial ingredient categories

Revision ID: 6d7c0be526eb
Revises: 431a799ebeb8
Create Date: 2026-01-27 22:28:20.881645

"""

from alembic import op
import sqlalchemy as sa


revision = "6d7c0be526eb"
down_revision = "431a799ebeb8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make migration idempotent - check if data already exists
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT COUNT(*) FROM ingredient_categories"))
    count = result.scalar()

    if count > 0:
        # Data already seeded, skip
        return

    # Create ingredient_categories table reference
    ingredient_categories = sa.table(
        "ingredient_categories",
        sa.column("name", sa.String),
        sa.column("normalized_name", sa.String),
        sa.column("level", sa.Integer),
        sa.column("parent_id", sa.Integer),
        sa.column("description", sa.Text),
    )

    # Insert root-level categories (level 0)
    op.bulk_insert(
        ingredient_categories,
        [
            {
                "name": "Dairy",
                "normalized_name": "dairy",
                "level": 0,
                "parent_id": None,
                "description": "Milk and milk-derived products including cheese, yogurt, butter, and cream",
            },
            {
                "name": "Grains",
                "normalized_name": "grains",
                "level": 0,
                "parent_id": None,
                "description": "Cereal grains and grain-based products including wheat, rice, oats, and bread",
            },
            {
                "name": "Proteins",
                "normalized_name": "proteins",
                "level": 0,
                "parent_id": None,
                "description": "Protein-rich foods including meat, poultry, fish, eggs, and plant proteins",
            },
            {
                "name": "Vegetables",
                "normalized_name": "vegetables",
                "level": 0,
                "parent_id": None,
                "description": "Plant-based vegetables including leafy greens, root vegetables, and cruciferous vegetables",
            },
            {
                "name": "Fruits",
                "normalized_name": "fruits",
                "level": 0,
                "parent_id": None,
                "description": "Fresh, dried, and processed fruits",
            },
            {
                "name": "Legumes",
                "normalized_name": "legumes",
                "level": 0,
                "parent_id": None,
                "description": "Beans, lentils, peas, and other leguminous plants",
            },
            {
                "name": "Nuts & Seeds",
                "normalized_name": "nuts_seeds",
                "level": 0,
                "parent_id": None,
                "description": "Tree nuts, peanuts, and edible seeds",
            },
            {
                "name": "FODMAPs",
                "normalized_name": "fodmaps",
                "level": 0,
                "parent_id": None,
                "description": "Fermentable oligosaccharides, disaccharides, monosaccharides, and polyols - known digestive triggers",
            },
            {
                "name": "Oils & Fats",
                "normalized_name": "oils_fats",
                "level": 0,
                "parent_id": None,
                "description": "Cooking oils, butter, lard, and other added fats",
            },
            {
                "name": "Sweeteners",
                "normalized_name": "sweeteners",
                "level": 0,
                "parent_id": None,
                "description": "Sugar, honey, artificial sweeteners, and other sweetening agents",
            },
        ],
    )


def downgrade() -> None:
    # Delete all seed data
    op.execute("DELETE FROM ingredient_categories WHERE level = 0")
