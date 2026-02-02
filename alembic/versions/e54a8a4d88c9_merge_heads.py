"""merge_heads

Revision ID: e54a8a4d88c9
Revises: a1b2c3d4e5f6, a20f1e06adcf
Create Date: 2026-02-02 22:56:02.165215

"""
from alembic import op
import sqlalchemy as sa


revision = 'e54a8a4d88c9'
down_revision = ('a1b2c3d4e5f6', 'a20f1e06adcf')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
