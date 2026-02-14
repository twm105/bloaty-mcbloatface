"""UserFeedback model for unified user feedback across features."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class UserFeedback(Base):
    """Unified feedback storage for all rated features (meals, diagnosis, etc.)."""

    __tablename__ = "user_feedback"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Polymorphic reference
    feature_type = Column(String(50), nullable=False)  # "meal_analysis", "diagnosis_result", etc.
    feature_id = Column(Integer, nullable=False)       # ID in referenced table

    # Feedback data
    rating = Column(Integer, nullable=False)  # 0-5 stars
    feedback_text = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    user = relationship("User")

    __table_args__ = (
        Index('idx_user_feedback_feature', 'feature_type', 'feature_id'),
        Index('idx_user_feedback_user', 'user_id'),
        UniqueConstraint('user_id', 'feature_type', 'feature_id', name='uq_user_feedback'),
    )

    def __repr__(self):
        return f"<UserFeedback(id={self.id}, feature={self.feature_type}:{self.feature_id}, rating={self.rating})>"
