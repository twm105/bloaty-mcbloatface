"""Business logic for symptom management."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.symptom import Symptom


class SymptomService:
    """Service for symptom-related operations."""

    @staticmethod
    def create_symptom(
        db: Session,
        user_id: UUID,
        raw_description: str,
        structured_type: Optional[str] = None,
        severity: Optional[int] = None,
        notes: Optional[str] = None,
        clarification_history: Optional[list] = None,
        timestamp: Optional[datetime] = None
    ) -> Symptom:
        """
        Create a new symptom entry.

        Args:
            db: Database session
            user_id: User ID
            raw_description: User's original symptom description
            structured_type: Categorized symptom type (e.g., "bloating", "nausea")
            severity: Severity rating 1-10
            notes: Additional notes
            clarification_history: Q&A history from AI clarification
            timestamp: Symptom timestamp (defaults to now)

        Returns:
            Created Symptom object
        """
        symptom = Symptom(
            user_id=user_id,
            raw_description=raw_description,
            structured_type=structured_type,
            severity=severity,
            notes=notes,
            clarification_history=clarification_history or [],
            timestamp=timestamp or datetime.utcnow()
        )
        db.add(symptom)
        db.commit()
        db.refresh(symptom)
        return symptom

    @staticmethod
    def get_symptom(db: Session, symptom_id: int) -> Optional[Symptom]:
        """Get a symptom by ID."""
        return db.query(Symptom).filter(Symptom.id == symptom_id).first()

    @staticmethod
    def get_user_symptoms(
        db: Session,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0
    ) -> List[Symptom]:
        """Get all symptoms for a user, ordered by timestamp descending."""
        return db.query(Symptom).filter(
            Symptom.user_id == user_id
        ).order_by(
            Symptom.timestamp.desc()
        ).limit(limit).offset(offset).all()

    @staticmethod
    def update_symptom(
        db: Session,
        symptom_id: int,
        raw_description: Optional[str] = None,
        structured_type: Optional[str] = None,
        severity: Optional[int] = None,
        notes: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ) -> Optional[Symptom]:
        """
        Update symptom details.

        Args:
            db: Database session
            symptom_id: Symptom ID
            raw_description: Updated description
            structured_type: Updated type
            severity: Updated severity
            notes: Updated notes
            timestamp: Updated timestamp

        Returns:
            Updated Symptom object or None if not found
        """
        symptom = db.query(Symptom).filter(Symptom.id == symptom_id).first()
        if not symptom:
            return None

        if raw_description is not None:
            symptom.raw_description = raw_description
        if structured_type is not None:
            symptom.structured_type = structured_type
        if severity is not None:
            symptom.severity = severity
        if notes is not None:
            symptom.notes = notes
        if timestamp is not None:
            symptom.timestamp = timestamp

        db.commit()
        db.refresh(symptom)
        return symptom

    @staticmethod
    def delete_symptom(db: Session, symptom_id: int) -> bool:
        """
        Delete a symptom.

        Args:
            db: Database session
            symptom_id: Symptom ID

        Returns:
            True if deleted, False if not found
        """
        symptom = db.query(Symptom).filter(Symptom.id == symptom_id).first()
        if symptom:
            db.delete(symptom)
            db.commit()
            return True
        return False

    @staticmethod
    def get_common_symptom_types() -> List[str]:
        """
        Get list of common gastro symptom types for dropdown.

        Returns:
            List of common symptom type strings
        """
        return [
            "Bloating",
            "Gas",
            "Stomach Pain",
            "Abdominal Cramps",
            "Nausea",
            "Diarrhea",
            "Constipation",
            "Heartburn",
            "Acid Reflux",
            "Indigestion",
            "Vomiting",
            "Loss of Appetite",
            "Other"
        ]


# Singleton instance
symptom_service = SymptomService()
