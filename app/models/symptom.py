from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Index,
    Boolean,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class Symptom(Base):
    """Symptom logging with conversational AI clarification and structured data extraction."""

    __tablename__ = "symptoms"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    timestamp = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Natural language input
    raw_description = Column(Text, nullable=False)  # User's original description

    # AI clarification process
    clarification_history = Column(
        JSONB, default=list
    )  # Array of {question: str, answer: str, skipped: bool}

    # Structured extraction from AI
    structured_type = Column(String(255))  # e.g., "bloating", "nausea", "stomach pain"
    severity = Column(Integer)  # 1-10 scale
    notes = Column(Text)  # Additional structured notes from AI extraction

    # Tag-based symptom tracking (new schema)
    tags = Column(JSONB)  # [{"name": "bloating", "severity": 7}, ...]
    start_time = Column(DateTime(timezone=True), nullable=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    episode_id = Column(Integer, ForeignKey("symptoms.id"), nullable=True)

    # AI elaboration tracking (deprecated fields - replaced by ai_generated_text/final_notes)
    ai_elaborated = Column(Boolean, default=False)
    ai_elaboration_response = Column(Text, nullable=True)  # Raw AI response for evals
    user_edited_elaboration = Column(Boolean, default=False)

    # New AI notes tracking (preferred over deprecated fields above)
    ai_generated_text = Column(Text, nullable=True)  # Original unedited AI response
    final_notes = Column(
        Text, nullable=True
    )  # User-edited version (or same as AI if not edited)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="symptoms")
    continuation_of = relationship(
        "Symptom", remote_side=[id], foreign_keys=[episode_id], backref="continuations"
    )

    __table_args__ = (
        Index("idx_symptoms_user_id", "user_id"),
        Index("idx_symptoms_timestamp", "timestamp"),
        Index("idx_symptoms_structured_type", "structured_type"),
        Index("idx_symptoms_episode_id", "episode_id"),
        Index("idx_symptoms_user_start_time", "user_id", "start_time"),
    )
