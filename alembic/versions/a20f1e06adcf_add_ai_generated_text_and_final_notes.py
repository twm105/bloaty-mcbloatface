"""add_ai_generated_text_and_final_notes

Revision ID: a20f1e06adcf
Revises: c362f51a0834
Create Date: 2026-01-30 23:19:26.759694

"""
from alembic import op
import sqlalchemy as sa


revision = 'a20f1e06adcf'
down_revision = 'c362f51a0834'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns
    op.add_column('symptoms', sa.Column('ai_generated_text', sa.Text(), nullable=True))
    op.add_column('symptoms', sa.Column('final_notes', sa.Text(), nullable=True))

    # Migrate existing data
    # For AI-elaborated symptoms: copy ai_elaboration_response to both fields
    op.execute("""
        UPDATE symptoms
        SET ai_generated_text = ai_elaboration_response,
            final_notes = CASE
                WHEN notes IS NOT NULL AND notes != '' THEN notes
                ELSE ai_elaboration_response
            END
        WHERE ai_elaborated = true
    """)

    # For manual notes (no AI): copy notes to final_notes only
    op.execute("""
        UPDATE symptoms
        SET final_notes = notes
        WHERE (ai_elaborated = false OR ai_elaborated IS NULL)
          AND notes IS NOT NULL
          AND notes != ''
    """)


def downgrade() -> None:
    # Drop new columns
    op.drop_column('symptoms', 'final_notes')
    op.drop_column('symptoms', 'ai_generated_text')
