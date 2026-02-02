"""DiagnosisCitation model for medical evidence."""
from sqlalchemy import Column, Integer, String, ForeignKey, Numeric, Text
from sqlalchemy.orm import relationship
from app.database import Base


class DiagnosisCitation(Base):
    """Stores medical citations for diagnosis results."""

    __tablename__ = "diagnosis_citations"

    id = Column(Integer, primary_key=True, index=True)
    result_id = Column(Integer, ForeignKey("diagnosis_results.id", ondelete="CASCADE"), nullable=False, index=True)

    # Citation metadata
    source_url = Column(String, nullable=False)
    source_title = Column(String, nullable=False)
    source_type = Column(String, nullable=False)  # 'nih', 'medical_journal', 'rd_site', 'other'
    snippet = Column(Text, nullable=True)  # Brief excerpt for hover tooltip
    relevance_score = Column(Numeric(4, 2), nullable=True)  # 0.00-1.00

    # Relationships
    result = relationship("DiagnosisResult", back_populates="citations")

    def __repr__(self):
        return f"<DiagnosisCitation(id={self.id}, source_type={self.source_type}, title={self.source_title[:30]})>"
