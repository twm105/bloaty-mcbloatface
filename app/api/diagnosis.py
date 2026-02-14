"""Diagnosis API endpoints for ingredient-symptom correlation analysis."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Body
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel

from app.database import get_db
from app.models import DiagnosisRun, DiagnosisResult, DiscountedIngredient, UserFeedback
from app.models.user import User
from app.services.diagnosis_service import DiagnosisService
from app.services.diagnosis_queue_service import DiagnosisQueueService
from app.services.ai_service import ServiceUnavailableError, RateLimitError
from app.services.auth.dependencies import get_current_user
from app.config import settings


router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])
templates = Jinja2Templates(directory="app/templates")


class DiagnosisRequest(BaseModel):
    """Request model for running diagnosis."""

    date_range_start: datetime | None = None
    date_range_end: datetime | None = None
    min_meals: int | None = None  # Defaults to settings.diagnosis_min_meals
    min_symptom_occurrences: int | None = None  # Defaults to settings.diagnosis_min_symptom_occurrences
    web_search_enabled: bool = True
    async_mode: bool = True  # Enable async processing by default


class DiagnosisFeedbackRequest(BaseModel):
    """Request model for submitting feedback on diagnosis result."""

    result_id: int
    rating: int  # 0-5 stars
    feedback_text: str | None = None


@router.post("/analyze")
async def analyze_correlations(
    request: DiagnosisRequest = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Run diagnosis analysis on user's meal and symptom data.

    Uses HOLISTIC per-ingredient analysis: gathers ALL data for each ingredient
    (windowed by max occurrences) to make a comprehensive classification decision.

    Each analysis run clears previous results for a fresh start, then analyzes
    each correlated ingredient with its full context including co-occurrence data.

    Returns:
        JSON with run_id, status, and counts
    """
    # Default date ranges: last 90 days (used for data sufficiency check only)
    end_date = request.date_range_end or datetime.utcnow()
    start_date = request.date_range_start or (end_date - timedelta(days=90))

    # Create diagnosis service
    diagnosis_service = DiagnosisService(db)

    # Override minimum thresholds (resolve None to settings defaults)
    diagnosis_service.MIN_MEALS = request.min_meals if request.min_meals is not None else settings.diagnosis_min_meals
    diagnosis_service.MIN_SYMPTOM_OCCURRENCES = request.min_symptom_occurrences if request.min_symptom_occurrences is not None else settings.diagnosis_min_symptom_occurrences

    # Step 1: Check data sufficiency (fast)
    sufficient_data, meals_count, symptoms_count = diagnosis_service.check_data_sufficiency(
        user.id, start_date, end_date
    )

    if not sufficient_data:
        # Create minimal run record for insufficient data
        diagnosis_run = DiagnosisRun(
            user_id=user.id,
            run_timestamp=datetime.utcnow(),
            status="completed",
            meals_analyzed=meals_count,
            symptoms_analyzed=symptoms_count,
            date_range_start=start_date,
            date_range_end=end_date,
            sufficient_data=False,
            web_search_enabled=request.web_search_enabled,
        )
        db.add(diagnosis_run)
        db.commit()

        return {
            "run_id": diagnosis_run.id,
            "status": "completed",
            "sufficient_data": False,
            "meals_analyzed": meals_count,
            "symptoms_analyzed": symptoms_count,
            "total_ingredients": 0,
            "message": (
                f"Insufficient data. Need {diagnosis_service.MIN_MEALS} meals and "
                f"{diagnosis_service.MIN_SYMPTOM_OCCURRENCES} symptoms. "
                f"You have: {meals_count} meals, {symptoms_count} symptoms."
            ),
        }

    # Step 2: Find all ingredients with meaningful correlations (holistic approach)
    # This uses ALL data windowed by max occurrences, not date-filtered
    correlated_ingredient_ids = diagnosis_service.get_correlated_ingredient_ids(user.id)

    if not correlated_ingredient_ids:
        diagnosis_run = DiagnosisRun(
            user_id=user.id,
            run_timestamp=datetime.utcnow(),
            status="completed",
            meals_analyzed=meals_count,
            symptoms_analyzed=symptoms_count,
            date_range_start=start_date,
            date_range_end=end_date,
            sufficient_data=True,
            web_search_enabled=request.web_search_enabled,
        )
        db.add(diagnosis_run)
        db.commit()

        return {
            "run_id": diagnosis_run.id,
            "status": "completed",
            "sufficient_data": True,
            "meals_analyzed": meals_count,
            "symptoms_analyzed": symptoms_count,
            "total_ingredients": 0,
            "message": "No ingredient-symptom correlations found in your data.",
        }

    # Step 3: Clear previous diagnosis data for fresh holistic analysis
    # This ensures each run starts clean - no deduplication complexity
    db.query(DiagnosisRun).filter(DiagnosisRun.user_id == user.id).delete()
    db.commit()

    # Step 4: Gather holistic data for each correlated ingredient
    holistic_ingredients = []
    for ingredient_id in correlated_ingredient_ids:
        ingredient_data = diagnosis_service.get_holistic_ingredient_data(user.id, ingredient_id)
        if ingredient_data and ingredient_data.get("confidence_level") != "insufficient_data":
            holistic_ingredients.append(ingredient_data)

    # Sort by confidence score
    holistic_ingredients.sort(key=lambda x: x["confidence_score"], reverse=True)

    if not holistic_ingredients:
        diagnosis_run = DiagnosisRun(
            user_id=user.id,
            run_timestamp=datetime.utcnow(),
            status="completed",
            meals_analyzed=meals_count,
            symptoms_analyzed=symptoms_count,
            date_range_start=start_date,
            date_range_end=end_date,
            sufficient_data=True,
            web_search_enabled=request.web_search_enabled,
        )
        db.add(diagnosis_run)
        db.commit()

        return {
            "run_id": diagnosis_run.id,
            "status": "completed",
            "sufficient_data": True,
            "meals_analyzed": meals_count,
            "symptoms_analyzed": symptoms_count,
            "total_ingredients": 0,
            "message": "No ingredients met the confidence threshold for analysis.",
        }

    # Step 5: Create diagnosis run record
    diagnosis_run = DiagnosisRun(
        user_id=user.id,
        run_timestamp=datetime.utcnow(),
        status="pending",
        total_ingredients=len(holistic_ingredients),
        completed_ingredients=0,
        meals_analyzed=meals_count,
        symptoms_analyzed=symptoms_count,
        date_range_start=start_date,
        date_range_end=end_date,
        sufficient_data=True,
        web_search_enabled=request.web_search_enabled,
    )
    db.add(diagnosis_run)
    db.commit()
    db.refresh(diagnosis_run)

    if request.async_mode:
        # Step 6: Enqueue async tasks with holistic data (returns immediately)
        queue_service = DiagnosisQueueService(db)
        tasks_enqueued = queue_service.enqueue_diagnosis(
            diagnosis_run=diagnosis_run,
            scored_ingredients=holistic_ingredients,
            web_search_enabled=request.web_search_enabled,
        )

        return {
            "run_id": diagnosis_run.id,
            "status": "processing",
            "sufficient_data": True,
            "meals_analyzed": meals_count,
            "symptoms_analyzed": symptoms_count,
            "total_ingredients": len(holistic_ingredients),
            "message": f"Analysis started. Analyzing {len(holistic_ingredients)} potential trigger ingredients.",
        }
    else:
        # Sync mode (legacy) - run full analysis
        try:
            diagnosis_run = await diagnosis_service.run_diagnosis(
                user_id=user.id,
                date_range_start=start_date,
                date_range_end=end_date,
                web_search_enabled=request.web_search_enabled,
            )
        except ServiceUnavailableError as e:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "service_unavailable",
                    "message": (
                        "The analysis service is experiencing connectivity issues. "
                        "This is usually temporary - please try again in a minute. "
                        "If the problem persists, try disabling web search for faster results."
                    ),
                    "can_retry": True,
                    "disable_web_search_option": True
                }
            )
        except RateLimitError as e:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limit",
                    "message": "Too many requests. Please wait a minute and try again.",
                    "can_retry": True
                }
            )
        except ValueError as e:
            error_msg = str(e)
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "validation_error",
                    "message": error_msg,
                    "can_retry": True,
                    "reduce_date_range_suggestion": "Request too large" in error_msg
                }
            )

        results_count = len(diagnosis_run.results) if diagnosis_run.results else 0

        return {
            "run_id": diagnosis_run.id,
            "status": "completed",
            "sufficient_data": diagnosis_run.sufficient_data,
            "meals_analyzed": diagnosis_run.meals_analyzed,
            "symptoms_analyzed": diagnosis_run.symptoms_analyzed,
            "results_count": results_count,
            "message": f"Analysis complete. Found {results_count} potential trigger ingredients.",
        }


@router.get("", response_class=HTMLResponse)
async def get_diagnosis(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Show diagnosis results page.

    With holistic analysis, each run clears previous data, so we simply
    show the single latest run's results (no deduplication needed).
    """
    # Get latest diagnosis run for user with all related data
    latest_run = (
        db.query(DiagnosisRun)
        .filter(DiagnosisRun.user_id == user.id)
        .order_by(DiagnosisRun.run_timestamp.desc())
        .options(
            joinedload(DiagnosisRun.results)
            .joinedload(DiagnosisResult.ingredient),
            joinedload(DiagnosisRun.results)
            .joinedload(DiagnosisResult.citations),
            # Note: feedback is now in unified user_feedback table
            joinedload(DiagnosisRun.discounted_ingredients)
            .joinedload(DiscountedIngredient.ingredient),
            joinedload(DiagnosisRun.discounted_ingredients)
            .joinedload(DiscountedIngredient.confounded_by),
        )
        .first()
    )

    # If no diagnosis run or insufficient data, show insufficient data page
    if not latest_run or not latest_run.sufficient_data:
        diagnosis_service = DiagnosisService(db)
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=90)

        _, meals_count, symptoms_count = diagnosis_service.check_data_sufficiency(
            user.id, start_date, end_date
        )

        return templates.TemplateResponse(
            "diagnosis/insufficient_data.html",
            {
                "request": request,
                "user": user,
                "meals_count": meals_count,
                "symptoms_count": symptoms_count,
                "min_meals": diagnosis_service.MIN_MEALS,
                "min_symptoms": diagnosis_service.MIN_SYMPTOM_OCCURRENCES,
            },
        )

    # Get results and discounted ingredients directly from the run
    # No deduplication needed since each analysis clears previous data
    results = sorted(
        latest_run.results or [],
        key=lambda r: r.confidence_score,
        reverse=True
    )

    discounted = latest_run.discounted_ingredients or []

    # Load feedback for all results from unified user_feedback table
    result_ids = [r.id for r in results]
    feedback_records = (
        db.query(UserFeedback)
        .filter(
            UserFeedback.user_id == user.id,
            UserFeedback.feature_type == "diagnosis_result",
            UserFeedback.feature_id.in_(result_ids),
        )
        .all()
    ) if result_ids else []

    # Build feedback lookup by result_id
    feedback_by_result = {f.feature_id: f for f in feedback_records}

    # Show results page with run_id for SSE streaming
    return templates.TemplateResponse(
        "diagnosis/results.html",
        {
            "request": request,
            "user": user,
            "diagnosis_run": latest_run,
            "results": results,
            "discounted": discounted,
            "run_id": latest_run.id,
            "run_status": latest_run.status,
            "total_ingredients": latest_run.total_ingredients,
            "completed_ingredients": latest_run.completed_ingredients,
            "has_new_data": False,  # Holistic analysis always starts fresh
            "feedback_by_result": feedback_by_result,  # Feedback lookup
        },
    )


@router.post("/feedback")
async def submit_feedback(
    request: DiagnosisFeedbackRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Submit user feedback on a diagnosis result.

    Validates rating range (0-5) and stores feedback in unified user_feedback table.
    """
    # Validate rating
    if not 0 <= request.rating <= 5:
        raise HTTPException(status_code=400, detail="Rating must be between 0 and 5")

    # Verify result exists and belongs to user
    result = (
        db.query(DiagnosisResult)
        .join(DiagnosisRun)
        .filter(
            DiagnosisResult.id == request.result_id, DiagnosisRun.user_id == user.id
        )
        .first()
    )

    if not result:
        raise HTTPException(status_code=404, detail="Diagnosis result not found")

    # Check if feedback already exists in unified table
    existing_feedback = (
        db.query(UserFeedback)
        .filter(
            UserFeedback.user_id == user.id,
            UserFeedback.feature_type == "diagnosis_result",
            UserFeedback.feature_id == request.result_id,
        )
        .first()
    )

    if existing_feedback:
        # Update existing feedback
        existing_feedback.rating = request.rating
        existing_feedback.feedback_text = request.feedback_text
        existing_feedback.created_at = datetime.utcnow()
    else:
        # Create new feedback in unified table
        feedback = UserFeedback(
            user_id=user.id,
            feature_type="diagnosis_result",
            feature_id=request.result_id,
            rating=request.rating,
            feedback_text=request.feedback_text,
        )
        db.add(feedback)

    db.commit()

    return {"message": "Feedback submitted successfully"}


@router.get("/methodology", response_class=HTMLResponse)
async def get_methodology(request: Request, user: User = Depends(get_current_user)):
    """
    Show methodology explanation page.

    Explains how diagnosis works in plain language.
    """
    return templates.TemplateResponse(
        "diagnosis/methodology.html", {"request": request, "user": user}
    )


@router.post("/reset")
async def reset_diagnosis_data(
    user: User = Depends(get_current_user),
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
            .filter(DiagnosisRun.user_id == user.id)
            .count()
        )

        # Delete all diagnosis runs (cascades to results, citations, feedback)
        db.query(DiagnosisRun).filter(
            DiagnosisRun.user_id == user.id
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
    user: User = Depends(get_current_user),
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
            DiagnosisRun.user_id == user.id
        )
        .first()
    )

    if not result:
        raise HTTPException(status_code=404, detail="Diagnosis result not found")

    # Delete result (cascades to citations and feedback)
    db.delete(result)
    db.commit()

    return Response(status_code=200)
