from sqlalchemy import Column, Integer, String, Text, DateTime, Numeric, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base


class EvalRun(Base):
    """Evaluation run results for tracking AI model performance over time."""
    __tablename__ = "eval_runs"

    id = Column(Integer, primary_key=True)
    model_name = Column(String(100), nullable=False)  # e.g., "claude-3-5-haiku-20241022"
    eval_type = Column(String(50), nullable=False)  # e.g., "ingredient_detection", "symptom_clarification"

    # Metrics
    precision = Column(Numeric(5, 4))
    recall = Column(Numeric(5, 4))
    f1_score = Column(Numeric(5, 4))
    accuracy = Column(Numeric(5, 4))

    # Test details
    num_test_cases = Column(Integer)
    test_data_source = Column(String(255))  # e.g., "bbc_good_food"
    detailed_results = Column(JSONB)  # Full results for each test case

    # Execution metadata
    execution_time_seconds = Column(Numeric(8, 2))
    notes = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('idx_eval_runs_model_name', 'model_name'),
        Index('idx_eval_runs_eval_type', 'eval_type'),
        Index('idx_eval_runs_created_at', 'created_at'),
    )
