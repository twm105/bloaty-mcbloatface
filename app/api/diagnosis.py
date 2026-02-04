"""Diagnosis API endpoints for ingredient-symptom correlation analysis."""
from datetime import datetime, timedelta
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Body
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel

from app.database import get_db
from app.models import DiagnosisRun, DiagnosisResult
from app.services.diagnosis_service import DiagnosisService


router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])
templates = Jinja2Templates(directory="app/templates")

# MVP single-user ID
MVP_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


class DiagnosisRequest(BaseModel):
    """Request model for running diagnosis."""

    date_range_start: datetime | None = None
    date_range_end: datetime | None = None
    min_meals: int = 1  # Lowered for testing to match service defaults
    min_symptom_occurrences: int = 1  # Lowered for testing to match service defaults
    web_search_enabled: bool = True


class DiagnosisFeedbackRequest(BaseModel):
    """Request model for submitting feedback on diagnosis result."""

    result_id: int
    rating: int  # 0-5 stars
    feedback_text: str | None = None


@router.post("/analyze")
async def analyze_correlations(
    request: DiagnosisRequest = Body(...),
    db: Session = Depends(get_db),
):
    """
    Run diagnosis analysis on user's meal and symptom data.

    Returns:
        JSON with run_id, data sufficiency status, counts, and result summary
    """
    # Default date ranges: last 90 days
    end_date = request.date_range_end or datetime.utcnow()
    start_date = request.date_range_start or (end_date - timedelta(days=90))

    # Create diagnosis service
    diagnosis_service = DiagnosisService(db)

    # Override minimum thresholds if provided
    if request.min_meals:
        diagnosis_service.MIN_MEALS = request.min_meals
    if request.min_symptom_occurrences:
        diagnosis_service.MIN_SYMPTOM_OCCURRENCES = request.min_symptom_occurrences

    # Run diagnosis
    diagnosis_run = await diagnosis_service.run_diagnosis(
        user_id=MVP_USER_ID,
        date_range_start=start_date,
        date_range_end=end_date,
        web_search_enabled=request.web_search_enabled,
    )

    # Get results count
    results_count = len(diagnosis_run.results) if diagnosis_run.results else 0

    return {
        "run_id": diagnosis_run.id,
        "sufficient_data": diagnosis_run.sufficient_data,
        "meals_analyzed": diagnosis_run.meals_analyzed,
        "symptoms_analyzed": diagnosis_run.symptoms_analyzed,
        "results_count": results_count,
        "message": (
            f"Analysis complete. Found {results_count} potential trigger ingredients."
            if diagnosis_run.sufficient_data
            else f"Insufficient data. Need {diagnosis_service.MIN_MEALS} meals and "
            f"{diagnosis_service.MIN_SYMPTOM_OCCURRENCES} symptoms. "
            f"You have: {diagnosis_run.meals_analyzed} meals, {diagnosis_run.symptoms_analyzed} symptoms."
        ),
    }


@router.get("", response_class=HTMLResponse)
async def get_diagnosis(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Show diagnosis results page.

    If sufficient data exists, shows latest diagnosis results.
    Otherwise, shows insufficient data page with progress indicators.
    """
    # Get latest diagnosis run for user
    latest_run = (
        db.query(DiagnosisRun)
        .filter(DiagnosisRun.user_id == MVP_USER_ID)
        .order_by(DiagnosisRun.run_timestamp.desc())
        .options(
            joinedload(DiagnosisRun.results)
            .joinedload(DiagnosisResult.ingredient),
            joinedload(DiagnosisRun.results)
            .joinedload(DiagnosisResult.citations),
            joinedload(DiagnosisRun.results)
            .joinedload(DiagnosisResult.feedback),
        )
        .first()
    )

    # If no diagnosis run or insufficient data, show insufficient data page
    if not latest_run or not latest_run.sufficient_data:
        # Get current counts for progress indicators
        diagnosis_service = DiagnosisService(db)
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=90)

        _, meals_count, symptoms_count = diagnosis_service.check_data_sufficiency(
            MVP_USER_ID, start_date, end_date
        )

        return templates.TemplateResponse(
            "diagnosis/insufficient_data.html",
            {
                "request": request,
                "meals_count": meals_count,
                "symptoms_count": symptoms_count,
                "min_meals": diagnosis_service.MIN_MEALS,
                "min_symptoms": diagnosis_service.MIN_SYMPTOM_OCCURRENCES,
            },
        )

    # Show results page
    return templates.TemplateResponse(
        "diagnosis/results.html",
        {
            "request": request,
            "diagnosis_run": latest_run,
            "results": latest_run.results,
        },
    )


@router.post("/feedback")
async def submit_feedback(
    request: DiagnosisFeedbackRequest,
    db: Session = Depends(get_db),
):
    """
    Submit user feedback on a diagnosis result.

    Validates rating range (0-5) and stores feedback in database.
    """
    from app.models import DiagnosisFeedback

    # Validate rating
    if not 0 <= request.rating <= 5:
        raise HTTPException(status_code=400, detail="Rating must be between 0 and 5")

    # Verify result exists and belongs to user
    result = (
        db.query(DiagnosisResult)
        .join(DiagnosisRun)
        .filter(
            DiagnosisResult.id == request.result_id, DiagnosisRun.user_id == MVP_USER_ID
        )
        .first()
    )

    if not result:
        raise HTTPException(status_code=404, detail="Diagnosis result not found")

    # Check if feedback already exists
    existing_feedback = (
        db.query(DiagnosisFeedback)
        .filter(
            DiagnosisFeedback.result_id == request.result_id,
            DiagnosisFeedback.user_id == MVP_USER_ID,
        )
        .first()
    )

    if existing_feedback:
        # Update existing feedback
        existing_feedback.rating = request.rating
        existing_feedback.feedback_text = request.feedback_text
        existing_feedback.created_at = datetime.utcnow()
    else:
        # Create new feedback
        feedback = DiagnosisFeedback(
            result_id=request.result_id,
            user_id=MVP_USER_ID,
            rating=request.rating,
            feedback_text=request.feedback_text,
        )
        db.add(feedback)

    db.commit()

    return {"message": "Feedback submitted successfully"}


@router.get("/methodology", response_class=HTMLResponse)
async def get_methodology(request: Request):
    """
    Show methodology explanation page.

    Explains how diagnosis works in plain language.
    """
    return templates.TemplateResponse(
        "diagnosis/methodology.html", {"request": request}
    )


@router.post("/reset")
async def reset_diagnosis_data(
    db: Session = Depends(get_db),
):
    """
    Reset all diagnosis data for the user.

    Deletes all DiagnosisRuns and cascades to related results, citations, and feedback.
    This is a destructive action that cannot be undone.

    Returns:
        JSON with success message and count of deleted runs
    """
    try:
        # Count runs before deletion for confirmation message
        runs_count = (
            db.query(DiagnosisRun)
            .filter(DiagnosisRun.user_id == MVP_USER_ID)
            .count()
        )

        # Delete all diagnosis runs (cascades to results, citations, feedback)
        db.query(DiagnosisRun).filter(
            DiagnosisRun.user_id == MVP_USER_ID
        ).delete()

        db.commit()

        return {
            "success": True,
            "message": f"Successfully deleted {runs_count} diagnosis run(s) and all associated data.",
            "runs_deleted": runs_count,
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset diagnosis data: {str(e)}"
        )


@router.delete("/results/{result_id}")
async def delete_diagnosis_result(
    result_id: int,
    db: Session = Depends(get_db),
):
    """
    Delete an individual diagnosis result.

    Removes one ingredient finding from a diagnosis run.
    Cascades to citations and feedback for that result.

    Returns:
        Empty 200 response (htmx will remove card from DOM)
    """
    # Verify result exists and belongs to user
    result = (
        db.query(DiagnosisResult)
        .join(DiagnosisRun)
        .filter(
            DiagnosisResult.id == result_id,
            DiagnosisRun.user_id == MVP_USER_ID
        )
        .first()
    )

    if not result:
        raise HTTPException(status_code=404, detail="Diagnosis result not found")

    # Delete result (cascades to citations and feedback)
    db.delete(result)
    db.commit()

    return Response(status_code=200)
