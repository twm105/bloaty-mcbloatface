from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, UniqueConstraint, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class IngredientCategoryRelation(Base):
    """Many-to-many relationship between ingredients and categories with confidence tracking."""
    __tablename__ = "ingredient_category_relations"

    id = Column(Integer, primary_key=True)
    ingredient_id = Column(Integer, ForeignKey('ingredients.id', ondelete='CASCADE'), nullable=False)
    category_id = Column(Integer, ForeignKey('ingredient_categories.id', ondelete='CASCADE'), nullable=False)
    confidence = Column(Numeric(3, 2), default=1.0)  # How certain is this categorization?
    source = Column(String(50), default='manual')  # 'manual', 'ai_inferred', 'user_defined'
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    ingredient = relationship("Ingredient", back_populates="category_relations")
    category = relationship("IngredientCategory", back_populates="ingredient_relations")

    __table_args__ = (
        UniqueConstraint('ingredient_id', 'category_id', name='uq_ingredient_category'),
        Index('idx_ingr_cat_rel_ingredient_id', 'ingredient_id'),
        Index('idx_ingr_cat_rel_category_id', 'category_id'),
    )
