from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class Meal(Base):
    """Meal logging with optional image and AI analysis results."""

    __tablename__ = "meals"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(255))  # AI-suggested meal name (user editable)
    name_source = Column(
        String(20), nullable=True
    )  # 'ai', 'user-edit', or None for manual entry
    status = Column(
        String(20), nullable=False, default="draft"
    )  # 'draft' or 'published'
    timestamp = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    country = Column(
        String(100)
    )  # Optional: where meal was consumed (e.g., "USA", "France", "Japan")
    local_timezone = Column(
        String(50)
    )  # IANA timezone at logging time (e.g., 'Asia/Tokyo', 'America/New_York')
    image_path = Column(String(512))  # Path to uploaded meal image
    meal_image_crop_x = Column(
        Float, default=50.0
    )  # X coordinate for circular crop (percentage from left)
    meal_image_crop_y = Column(
        Float, default=50.0
    )  # Y coordinate for circular crop (percentage from top)
    user_notes = Column(Text)  # User's own notes about the meal
    ai_raw_response = Column(Text)  # Raw JSON response from Claude for debugging
    ai_suggested_ingredients = Column(
        JSONB
    )  # Original AI suggestions for evals/data science
    copied_from_id = Column(
        Integer, ForeignKey("meals.id", ondelete="SET NULL"), nullable=True
    )  # Reference to original meal if this is a copy
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    @property
    def is_copy(self) -> bool:
        """Returns True if this meal was duplicated from another meal."""
        return self.copied_from_id is not None

    # Relationships
    user = relationship("User", back_populates="meals")
    meal_ingredients = relationship(
        "MealIngredient", back_populates="meal", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_meals_user_id", "user_id"),
        Index("idx_meals_timestamp", "timestamp"),
        Index("idx_meals_country", "country"),
        Index("idx_meals_copied_from_id", "copied_from_id"),
    )
