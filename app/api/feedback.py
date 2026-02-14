"""Unified feedback API endpoints for rating features (meals, diagnosis, etc.)."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.user_feedback import UserFeedback
from app.models.meal import Meal
from app.models.diagnosis_result import DiagnosisResult
from app.models.diagnosis_run import DiagnosisRun
from app.services.auth.dependencies import get_current_user


router = APIRouter(prefix="/feedback", tags=["feedback"])


# Valid feature types and their validation functions
FEATURE_VALIDATORS = {
    "meal_analysis": lambda db, user_id, feature_id: (
        db.query(Meal)
        .filter(Meal.id == feature_id, Meal.user_id == user_id)
        .first() is not None
    ),
    "diagnosis_result": lambda db, user_id, feature_id: (
        db.query(DiagnosisResult)
        .join(DiagnosisRun)
        .filter(DiagnosisResult.id == feature_id, DiagnosisRun.user_id == user_id)
        .first() is not None
    ),
}


@router.post("")
async def submit_feedback(
    feature_type: str = Form(...),
    feature_id: int = Form(...),
    rating: int = Form(...),
    feedback_text: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Submit feedback for any feature (meal analysis, diagnosis result, etc.).

    Upserts feedback record - creates new or updates existing.
    """
    # Validate rating range
    if not 0 <= rating <= 5:
        raise HTTPException(status_code=400, detail="Rating must be between 0 and 5")

    # Validate feature type
    if feature_type not in FEATURE_VALIDATORS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid feature_type. Must be one of: {list(FEATURE_VALIDATORS.keys())}"
        )

    # Validate that feature exists and belongs to user
    validator = FEATURE_VALIDATORS[feature_type]
    if not validator(db, user.id, feature_id):
        raise HTTPException(status_code=404, detail=f"{feature_type} not found")

    # Upsert feedback record
    existing_feedback = (
        db.query(UserFeedback)
        .filter(
            UserFeedback.user_id == user.id,
            UserFeedback.feature_type == feature_type,
            UserFeedback.feature_id == feature_id,
        )
        .first()
    )

    if existing_feedback:
        # Update existing feedback
        existing_feedback.rating = rating
        existing_feedback.feedback_text = feedback_text
        existing_feedback.created_at = datetime.utcnow()
    else:
        # Create new feedback
        feedback = UserFeedback(
            user_id=user.id,
            feature_type=feature_type,
            feature_id=feature_id,
            rating=rating,
            feedback_text=feedback_text,
        )
        db.add(feedback)

    db.commit()

    return {"message": "Feedback submitted successfully"}


@router.get("/{feature_type}/{feature_id}")
async def get_feedback(
    feature_type: str,
    feature_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get user's feedback for a specific feature."""
    feedback = (
        db.query(UserFeedback)
        .filter(
            UserFeedback.user_id == user.id,
            UserFeedback.feature_type == feature_type,
            UserFeedback.feature_id == feature_id,
        )
        .first()
    )

    if not feedback:
        return {"rating": 0, "feedback_text": None}

    return {
        "rating": feedback.rating,
        "feedback_text": feedback.feedback_text,
        "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
    }
