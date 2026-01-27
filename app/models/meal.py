from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class Meal(Base):
    """Meal logging with optional image and AI analysis results."""
    __tablename__ = "meals"

    id = Column(Integer, primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    country = Column(String(100))  # Optional: where meal was consumed (e.g., "USA", "France", "Japan")
    image_path = Column(String(512))  # Path to uploaded meal image
    user_notes = Column(Text)  # User's own notes about the meal
    ai_raw_response = Column(Text)  # Raw JSON response from Claude for debugging
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="meals")
    meal_ingredients = relationship("MealIngredient", back_populates="meal", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_meals_user_id', 'user_id'),
        Index('idx_meals_timestamp', 'timestamp'),
        Index('idx_meals_country', 'country'),
    )
