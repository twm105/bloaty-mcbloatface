"""DiagnosisRun model for tracking analysis execution."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class DiagnosisRun(Base):
    """Records each diagnosis analysis run with metadata."""

    __tablename__ = "diagnosis_runs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    run_timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    # Analysis scope
    meals_analyzed = Column(Integer, nullable=False)
    symptoms_analyzed = Column(Integer, nullable=False)
    date_range_start = Column(DateTime, nullable=False)
    date_range_end = Column(DateTime, nullable=False)

    # Data sufficiency
    sufficient_data = Column(Boolean, nullable=False, default=False)

    # Claude API metadata
    claude_model = Column(String, nullable=True)  # e.g., "claude-sonnet-4.5"
    cache_hit = Column(Boolean, nullable=False, default=False)
    input_tokens = Column(Integer, nullable=True)
    cached_tokens = Column(Integer, nullable=True)
    web_search_enabled = Column(Boolean, nullable=False, default=True)

    # Relationships
    user = relationship("User", back_populates="diagnosis_runs")
    results = relationship("DiagnosisResult", back_populates="run", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<DiagnosisRun(id={self.id}, user_id={self.user_id}, timestamp={self.run_timestamp})>"
