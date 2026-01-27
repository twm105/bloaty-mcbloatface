from sqlalchemy import Column, Integer, String, DateTime, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class Ingredient(Base):
    """Ingredient master table with normalized names for correlation analysis."""
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)  # Original name as entered/detected
    normalized_name = Column(String(255), nullable=False, unique=True, index=True)  # Lowercase, no spaces for matching
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    meal_ingredients = relationship("MealIngredient", back_populates="ingredient")
    category_relations = relationship("IngredientCategoryRelation", back_populates="ingredient", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_ingredients_normalized_name', 'normalized_name'),
    )

    @staticmethod
    def normalize_name(name: str) -> str:
        """Normalize ingredient name for consistent matching."""
        return name.lower().strip().replace(" ", "_").replace("-", "_")
