"""add_mq_tables_and_fields

Revision ID: 2a3b4c5d6e7f
Revises: 1c90b2c5ff87
Create Date: 2026-02-07

Adds:
- ai_usage_logs table for tracking AI API costs
- status/progress fields to diagnosis_runs for async processing
- structured summary fields to diagnosis_results for per-ingredient analysis
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "2a3b4c5d6e7f"
down_revision = "1c90b2c5ff87"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create ai_usage_logs table
    op.create_table(
        "ai_usage_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
        sa.Column("service_type", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_tokens", sa.Integer(), nullable=False),
        sa.Column(
            "estimated_cost_cents", sa.Numeric(precision=10, scale=4), nullable=False
        ),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("request_type", sa.String(), nullable=True),
        sa.Column("web_search_enabled", sa.Boolean(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_usage_logs_id"), "ai_usage_logs", ["id"], unique=False)
    op.create_index(
        op.f("ix_ai_usage_logs_user_id"), "ai_usage_logs", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_ai_usage_logs_timestamp"), "ai_usage_logs", ["timestamp"], unique=False
    )
    op.create_index(
        op.f("ix_ai_usage_logs_request_id"),
        "ai_usage_logs",
        ["request_id"],
        unique=False,
    )

    # Add async processing fields to diagnosis_runs
    op.add_column("diagnosis_runs", sa.Column("status", sa.String(), nullable=True))
    op.add_column(
        "diagnosis_runs", sa.Column("total_ingredients", sa.Integer(), nullable=True)
    )
    op.add_column(
        "diagnosis_runs",
        sa.Column("completed_ingredients", sa.Integer(), nullable=True),
    )
    op.add_column(
        "diagnosis_runs", sa.Column("started_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "diagnosis_runs", sa.Column("completed_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "diagnosis_runs", sa.Column("error_message", sa.Text(), nullable=True)
    )

    # Set default values for existing rows
    op.execute("UPDATE diagnosis_runs SET status = 'completed' WHERE status IS NULL")
    op.execute(
        "UPDATE diagnosis_runs SET completed_ingredients = 0 WHERE completed_ingredients IS NULL"
    )

    # Now make status non-nullable
    op.alter_column(
        "diagnosis_runs", "status", nullable=False, server_default="pending"
    )
    op.alter_column(
        "diagnosis_runs", "completed_ingredients", nullable=False, server_default="0"
    )

    # Add structured summary fields to diagnosis_results
    op.add_column(
        "diagnosis_results", sa.Column("diagnosis_summary", sa.Text(), nullable=True)
    )
    op.add_column(
        "diagnosis_results",
        sa.Column("recommendations_summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "diagnosis_results",
        sa.Column(
            "processing_suggestions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "diagnosis_results",
        sa.Column(
            "alternative_meals", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )


def downgrade() -> None:
    # Remove structured summary fields from diagnosis_results
    op.drop_column("diagnosis_results", "alternative_meals")
    op.drop_column("diagnosis_results", "processing_suggestions")
    op.drop_column("diagnosis_results", "recommendations_summary")
    op.drop_column("diagnosis_results", "diagnosis_summary")

    # Remove async processing fields from diagnosis_runs
    op.drop_column("diagnosis_runs", "error_message")
    op.drop_column("diagnosis_runs", "completed_at")
    op.drop_column("diagnosis_runs", "started_at")
    op.drop_column("diagnosis_runs", "completed_ingredients")
    op.drop_column("diagnosis_runs", "total_ingredients")
    op.drop_column("diagnosis_runs", "status")

    # Drop ai_usage_logs table
    op.drop_index(op.f("ix_ai_usage_logs_request_id"), table_name="ai_usage_logs")
    op.drop_index(op.f("ix_ai_usage_logs_timestamp"), table_name="ai_usage_logs")
    op.drop_index(op.f("ix_ai_usage_logs_user_id"), table_name="ai_usage_logs")
    op.drop_index(op.f("ix_ai_usage_logs_id"), table_name="ai_usage_logs")
    op.drop_table("ai_usage_logs")
