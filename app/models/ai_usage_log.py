"""AIUsageLog model for tracking AI API usage and costs."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class AIUsageLog(Base):
    """Tracks all AI API calls for cost monitoring and analytics."""

    __tablename__ = "ai_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # Service identification
    service_type = Column(String, nullable=False)  # 'meal_analysis', 'diagnosis', 'symptom_elaboration', etc.
    model = Column(String, nullable=False)  # e.g., 'claude-sonnet-4-5-20250929'

    # Token usage
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cached_tokens = Column(Integer, nullable=False, default=0)

    # Cost tracking (in cents for precision)
    estimated_cost_cents = Column(Numeric(10, 4), nullable=False, default=0)

    # Request linking
    request_id = Column(String, index=True, nullable=True)  # Links to diagnosis_run.id, meal.id, etc.
    request_type = Column(String, nullable=True)  # 'diagnosis_run', 'meal', 'symptom', etc.

    # Feature flags
    web_search_enabled = Column(Boolean, default=False)

    # Status
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)

    def __repr__(self):
        return f"<AIUsageLog(id={self.id}, service={self.service_type}, cost={self.estimated_cost_cents}c)>"
