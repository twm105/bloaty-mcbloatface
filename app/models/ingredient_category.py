from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class IngredientCategory(Base):
    """Hierarchical ingredient categorization for flexible analysis (e.g., Dairy > Cow's Milk > Whole Milk)."""

    __tablename__ = "ingredient_categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    normalized_name = Column(String(255), nullable=False, unique=True)
    parent_id = Column(
        Integer, ForeignKey("ingredient_categories.id", ondelete="CASCADE")
    )
    level = Column(Integer, nullable=False, default=0)  # 0=root, 1=first level, etc.
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Self-referential relationship for hierarchy
    parent = relationship("IngredientCategory", remote_side=[id], backref="children")

    # Relationship to ingredient mappings
    ingredient_relations = relationship(
        "IngredientCategoryRelation",
        back_populates="category",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_ingredient_categories_parent_id", "parent_id"),
        Index("idx_ingredient_categories_level", "level"),
    )

    @staticmethod
    def normalize_name(name: str) -> str:
        """Normalize category name for consistent matching."""
        return name.lower().strip().replace(" ", "_").replace("-", "_")
