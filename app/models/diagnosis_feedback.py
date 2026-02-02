"""DiagnosisFeedback model for user validation."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class DiagnosisFeedback(Base):
    """Stores user feedback on diagnosis results."""

    __tablename__ = "diagnosis_feedback"

    id = Column(Integer, primary_key=True, index=True)
    result_id = Column(Integer, ForeignKey("diagnosis_results.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Feedback data
    rating = Column(Integer, nullable=False)  # 0-5 stars
    feedback_text = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Future: elimination trial tracking
    eliminated = Column(Boolean, nullable=False, default=False)

    # Relationships
    result = relationship("DiagnosisResult", back_populates="feedback")
    user = relationship("User")

    def __repr__(self):
        return f"<DiagnosisFeedback(id={self.id}, result_id={self.result_id}, rating={self.rating})>"
