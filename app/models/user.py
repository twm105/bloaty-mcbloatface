from sqlalchemy import Column, String, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from app.database import Base


class User(Base):
    """User model for authentication and data ownership."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(
        String(255), unique=True, nullable=True
    )  # Nullable for MVP single-user
    password_hash = Column(String(255), nullable=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    meals = relationship("Meal", back_populates="user", cascade="all, delete-orphan")
    symptoms = relationship(
        "Symptom", back_populates="user", cascade="all, delete-orphan"
    )
    settings = relationship(
        "UserSettings",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    data_exports = relationship(
        "DataExport", back_populates="user", cascade="all, delete-orphan"
    )
    diagnosis_runs = relationship(
        "DiagnosisRun", back_populates="user", cascade="all, delete-orphan"
    )
    sessions = relationship(
        "Session", back_populates="user", cascade="all, delete-orphan"
    )
    invites_created = relationship(
        "Invite",
        foreign_keys="Invite.created_by",
        back_populates="creator",
        cascade="all, delete-orphan",
    )
