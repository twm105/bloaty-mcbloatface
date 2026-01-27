from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, Numeric, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum

from app.database import Base


class IngredientState(str, enum.Enum):
    """Enum for ingredient preparation state."""
    RAW = "raw"
    COOKED = "cooked"
    PROCESSED = "processed"


class MealIngredient(Base):
    """Junction table linking meals to ingredients with state and quantity tracking."""
    __tablename__ = "meal_ingredients"

    id = Column(Integer, primary_key=True)
    meal_id = Column(Integer, ForeignKey('meals.id', ondelete='CASCADE'), nullable=False)
    ingredient_id = Column(Integer, ForeignKey('ingredients.id', ondelete='CASCADE'), nullable=False)
    state = Column(Enum(IngredientState), nullable=False, default=IngredientState.RAW)
    quantity_description = Column(String(255))  # Free-text quantity (e.g., "2 cups", "100g", "a handful")
    confidence = Column(Numeric(3, 2))  # AI confidence score (0.0-1.0) if AI-detected
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    meal = relationship("Meal", back_populates="meal_ingredients")
    ingredient = relationship("Ingredient", back_populates="meal_ingredients")

    __table_args__ = (
        Index('idx_meal_ingredients_meal_id', 'meal_id'),
        Index('idx_meal_ingredients_ingredient_id', 'ingredient_id'),
    )
