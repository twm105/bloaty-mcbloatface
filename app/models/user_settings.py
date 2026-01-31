from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class UserSettings(Base):
    """User settings including GDPR consent tracking and optional demographics."""
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)

    # Medical Disclaimer
    disclaimer_acknowledged = Column(Boolean, default=False)
    disclaimer_acknowledged_at = Column(DateTime(timezone=True))

    # GDPR / Privacy Consent
    data_processing_consent = Column(Boolean, default=False)
    data_processing_consent_at = Column(DateTime(timezone=True))
    privacy_policy_version = Column(String(20))  # e.g., "1.0"

    # Optional Demographics (with explicit consent)
    demographics_consent = Column(Boolean, default=False)
    age = Column(Integer)
    weight_kg = Column(Numeric(5, 2))
    height_cm = Column(Integer)
    gender = Column(String(50))  # Free-text for inclusivity

    # AI Feature Preferences
    ai_elaborate_symptoms = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="settings")

    __table_args__ = (
        UniqueConstraint('user_id', name='uq_user_settings_user_id'),
    )
