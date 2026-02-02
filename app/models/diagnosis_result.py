"""DiagnosisResult model for ingredient-symptom correlations."""
from sqlalchemy import Column, Integer, String, ForeignKey, Numeric, Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database import Base


class DiagnosisResult(Base):
    """Stores ingredient-symptom correlation findings."""

    __tablename__ = "diagnosis_results"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("diagnosis_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False, index=True)

    # Confidence metrics
    confidence_score = Column(Numeric(5, 3), nullable=False)  # 0.000-1.000
    confidence_level = Column(String, nullable=False)  # 'high', 'medium', 'low', 'insufficient_data'

    # Temporal correlation counts
    immediate_correlation = Column(Integer, nullable=False, default=0)  # 0-2hr lag
    delayed_correlation = Column(Integer, nullable=False, default=0)    # 4-24hr lag
    cumulative_correlation = Column(Integer, nullable=False, default=0) # >24hr lag

    # Statistical metrics
    times_eaten = Column(Integer, nullable=False)
    times_followed_by_symptoms = Column(Integer, nullable=False)

    # Ingredient state analysis
    state_matters = Column(Boolean, nullable=False, default=False)
    problematic_states = Column(JSONB, nullable=True)  # ["raw", "cooked", "processed"]

    # Associated symptoms
    associated_symptoms = Column(JSONB, nullable=False)
    # Format: [{"name": str, "severity_avg": float, "frequency": int, "lag_hours": float}]

    # AI analysis
    ai_analysis = Column(Text, nullable=True)  # Claude's interpretation

    # Relationships
    run = relationship("DiagnosisRun", back_populates="results")
    ingredient = relationship("Ingredient")
    citations = relationship("DiagnosisCitation", back_populates="result", cascade="all, delete-orphan")
    feedback = relationship("DiagnosisFeedback", back_populates="result", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<DiagnosisResult(id={self.id}, ingredient_id={self.ingredient_id}, confidence={self.confidence_score})>"
