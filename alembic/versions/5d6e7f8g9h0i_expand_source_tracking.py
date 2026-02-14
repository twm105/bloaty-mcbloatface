"""expand_source_tracking

Revision ID: 5d6e7f8g9h0i
Revises: 4c5d6e7f8g9h
Create Date: 2026-02-14

Expands ingredient source tracking and creates unified feedback system:
- Add meals.name_source column for title provenance tracking
- Create unified user_feedback table (polymorphic)
- Migrate diagnosis_feedback data to user_feedback
- Update meal_ingredients.source: 'manual' -> 'user-add'
- Drop diagnosis_feedback table
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '5d6e7f8g9h0i'
down_revision = '4c5d6e7f8g9h'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add meals.name_source column
    op.add_column('meals', sa.Column('name_source', sa.String(20), nullable=True))

    # 2. Create user_feedback table
    op.create_table('user_feedback',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('feature_type', sa.String(50), nullable=False),
        sa.Column('feature_id', sa.Integer(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('feedback_text', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_feedback_id'), 'user_feedback', ['id'], unique=False)
    op.create_index('idx_user_feedback_feature', 'user_feedback', ['feature_type', 'feature_id'], unique=False)
    op.create_index('idx_user_feedback_user', 'user_feedback', ['user_id'], unique=False)
    op.create_unique_constraint('uq_user_feedback', 'user_feedback', ['user_id', 'feature_type', 'feature_id'])

    # 3. Migrate diagnosis_feedback data to user_feedback
    op.execute("""
        INSERT INTO user_feedback (user_id, feature_type, feature_id, rating, feedback_text, created_at)
        SELECT user_id, 'diagnosis_result', result_id, rating, feedback_text, created_at
        FROM diagnosis_feedback
    """)

    # 4. Update meal_ingredients.source: 'manual' -> 'user-add'
    op.execute("UPDATE meal_ingredients SET source = 'user-add' WHERE source = 'manual'")

    # 5. Set name_source for meals with AI analysis
    op.execute("""
        UPDATE meals
        SET name_source = 'ai'
        WHERE ai_suggested_ingredients IS NOT NULL AND name IS NOT NULL
    """)

    # 6. Drop diagnosis_feedback table
    op.drop_index(op.f('ix_diagnosis_feedback_user_id'), table_name='diagnosis_feedback')
    op.drop_index(op.f('ix_diagnosis_feedback_result_id'), table_name='diagnosis_feedback')
    op.drop_index(op.f('ix_diagnosis_feedback_id'), table_name='diagnosis_feedback')
    op.drop_table('diagnosis_feedback')


def downgrade() -> None:
    # 1. Recreate diagnosis_feedback table
    op.create_table('diagnosis_feedback',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('result_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('feedback_text', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('eliminated', sa.Boolean(), nullable=False, server_default='false'),
        sa.ForeignKeyConstraint(['result_id'], ['diagnosis_results.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_diagnosis_feedback_id'), 'diagnosis_feedback', ['id'], unique=False)
    op.create_index(op.f('ix_diagnosis_feedback_result_id'), 'diagnosis_feedback', ['result_id'], unique=False)
    op.create_index(op.f('ix_diagnosis_feedback_user_id'), 'diagnosis_feedback', ['user_id'], unique=False)

    # 2. Migrate data back from user_feedback to diagnosis_feedback
    op.execute("""
        INSERT INTO diagnosis_feedback (user_id, result_id, rating, feedback_text, created_at, eliminated)
        SELECT user_id, feature_id, rating, feedback_text, created_at, false
        FROM user_feedback
        WHERE feature_type = 'diagnosis_result'
    """)

    # 3. Revert meal_ingredients.source: 'user-add' -> 'manual'
    op.execute("UPDATE meal_ingredients SET source = 'manual' WHERE source = 'user-add'")

    # 4. Drop user_feedback table
    op.drop_constraint('uq_user_feedback', 'user_feedback', type_='unique')
    op.drop_index('idx_user_feedback_user', table_name='user_feedback')
    op.drop_index('idx_user_feedback_feature', table_name='user_feedback')
    op.drop_index(op.f('ix_user_feedback_id'), table_name='user_feedback')
    op.drop_table('user_feedback')

    # 5. Drop meals.name_source column
    op.drop_column('meals', 'name_source')
