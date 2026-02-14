"""DiscountedIngredient model for confounded ingredients that were analyzed but discarded."""

from sqlalchemy import Column, Integer, String, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database import Base


class DiscountedIngredient(Base):
    """
    Stores ingredients that were analyzed but discarded as confounders.

    IMPORTANT: Preserves ALL original analysis data so users can review the full
    context of why an ingredient was discarded. This transparency helps users
    understand and validate the diagnosis results.
    """

    __tablename__ = "discounted_ingredients"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(
        Integer,
        ForeignKey("diagnosis_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ingredient_id = Column(
        Integer,
        ForeignKey("ingredients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ===== DISCARD JUSTIFICATION =====
    # Claude's explanation of why this ingredient was discarded
    discard_justification = Column(Text, nullable=False)
    # Example: "DISCARDED: High co-occurrence with garlic (95%) combined with garlic being
    # a known high-FODMAP trigger. Potatoes are generally well-tolerated and low-FODMAP."

    # What ingredient this was confounded with
    confounded_by_ingredient_id = Column(
        Integer, ForeignKey("ingredients.id"), nullable=True
    )

    # ===== ORIGINAL CORRELATION DATA (from statistical analysis) =====
    original_confidence_score = Column(Numeric(5, 3), nullable=True)  # 0.000-1.000
    original_confidence_level = Column(String, nullable=True)  # 'high', 'medium', 'low'
    times_eaten = Column(Integer, nullable=True)
    times_followed_by_symptoms = Column(Integer, nullable=True)
    immediate_correlation = Column(Integer, nullable=True)  # 0-2hr lag count
    delayed_correlation = Column(Integer, nullable=True)  # 4-24hr lag count
    cumulative_correlation = Column(Integer, nullable=True)  # >24hr lag count
    associated_symptoms = Column(JSONB, nullable=True)
    # Format: [{"name": str, "severity_avg": float, "frequency": int}]

    # ===== CO-OCCURRENCE DATA =====
    conditional_probability = Column(
        Numeric(4, 3), nullable=True
    )  # P(this|confounded_by)
    reverse_probability = Column(Numeric(4, 3), nullable=True)  # P(confounded_by|this)
    lift = Column(Numeric(5, 2), nullable=True)
    cooccurrence_meals_count = Column(Integer, nullable=True)  # How many meals had both

    # ===== MEDICAL GROUNDING =====
    medical_grounding_summary = Column(Text, nullable=True)
    # Example: "Potatoes are low-FODMAP and rarely cause GI symptoms. They contain
    # resistant starch which can cause mild gas in some individuals but is generally
    # well-tolerated. No common allergens or intolerances associated."

    # Relationships
    run = relationship("DiagnosisRun", back_populates="discounted_ingredients")
    ingredient = relationship("Ingredient", foreign_keys=[ingredient_id])
    confounded_by = relationship(
        "Ingredient", foreign_keys=[confounded_by_ingredient_id]
    )

    def __repr__(self):
        return f"<DiscountedIngredient(id={self.id}, ingredient_id={self.ingredient_id}, confounded_by={self.confounded_by_ingredient_id})>"
