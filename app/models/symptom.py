from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class Symptom(Base):
    """Symptom logging with conversational AI clarification and structured data extraction."""
    __tablename__ = "symptoms"

    id = Column(Integer, primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Natural language input
    raw_description = Column(Text, nullable=False)  # User's original description

    # AI clarification process
    clarification_history = Column(JSONB, default=list)  # Array of {question: str, answer: str, skipped: bool}

    # Structured extraction from AI
    structured_type = Column(String(255))  # e.g., "bloating", "nausea", "stomach pain"
    severity = Column(Integer)  # 1-10 scale
    notes = Column(Text)  # Additional structured notes from AI extraction

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="symptoms")

    __table_args__ = (
        Index('idx_symptoms_user_id', 'user_id'),
        Index('idx_symptoms_timestamp', 'timestamp'),
        Index('idx_symptoms_structured_type', 'structured_type'),
    )
