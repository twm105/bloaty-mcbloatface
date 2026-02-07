"""Diagnosis API endpoints for ingredient-symptom correlation analysis."""
from datetime import datetime, timedelta
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Body
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from pydantic import BaseModel

from app.database import get_db
from app.models import DiagnosisRun, DiagnosisResult
from app.services.diagnosis_service import DiagnosisService
from app.services.diagnosis_queue_service import DiagnosisQueueService
from app.services.ai_service import ServiceUnavailableError, RateLimitError
from app.config import settings


router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])
templates = Jinja2Templates(directory="app/templates")

# MVP single-user ID
MVP_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


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
    db: Session = Depends(get_db),
):
    """
    Run diagnosis analysis on user's meal and symptom data.

    In async mode (default), this returns immediately with a run_id
    and the client should connect to the SSE stream for updates.

    In sync mode, this blocks until analysis is complete (legacy behavior).

    Returns:
        JSON with run_id, status, and counts
    """
    # Default date ranges: last 90 days
    end_date = request.date_range_end or datetime.utcnow()
    start_date = request.date_range_start or (end_date - timedelta(days=90))

    # Create diagnosis service
    diagnosis_service = DiagnosisService(db)

    # Override minimum thresholds (resolve None to settings defaults)
    diagnosis_service.MIN_MEALS = request.min_meals if request.min_meals is not None else settings.diagnosis_min_meals
    diagnosis_service.MIN_SYMPTOM_OCCURRENCES = request.min_symptom_occurrences if request.min_symptom_occurrences is not None else settings.diagnosis_min_symptom_occurrences

    # Step 1: Check data sufficiency (fast)
    sufficient_data, meals_count, symptoms_count = diagnosis_service.check_data_sufficiency(
        MVP_USER_ID, start_date, end_date
    )

    if not sufficient_data:
        # Create minimal run record for insufficient data
        diagnosis_run = DiagnosisRun(
            user_id=MVP_USER_ID,
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

    # Step 2: Run temporal windowing queries (fast SQL)
    correlations = diagnosis_service.get_temporal_correlations(
        MVP_USER_ID, start_date, end_date
    )

    if not correlations:
        diagnosis_run = DiagnosisRun(
            user_id=MVP_USER_ID,
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

    # Step 3: Aggregate and calculate confidence scores (fast)
    aggregated = diagnosis_service.aggregate_correlations_by_ingredient(correlations)

    scored_ingredients = []
    for key, data in aggregated.items():
        confidence_score, confidence_level = diagnosis_service.calculate_confidence(
            times_eaten=data["times_eaten"],
            symptom_occurrences=data["total_symptom_occurrences"],
            immediate_count=data["immediate_total"],
            delayed_count=data["delayed_total"],
            cumulative_count=data["cumulative_total"],
            avg_severity=sum(s["severity_avg"] for s in data["associated_symptoms"])
            / len(data["associated_symptoms"])
            if data["associated_symptoms"]
            else 0,
        )

        if confidence_level != "insufficient_data":
            scored_ingredients.append({
                **data,
                "confidence_score": confidence_score,
                "confidence_level": confidence_level,
            })

    scored_ingredients.sort(key=lambda x: x["confidence_score"], reverse=True)

    # Step 3.5: Filter out ingredients that already have results from previous runs
    existing_ingredient_ids = set(
        row[0] for row in db.query(DiagnosisResult.ingredient_id)
        .join(DiagnosisRun)
        .filter(
            DiagnosisRun.user_id == MVP_USER_ID,
            DiagnosisRun.status == "completed"
        )
        .distinct()
        .all()
    )

    # Filter to only unanalyzed ingredients
    unanalyzed_ingredients = [
        ing for ing in scored_ingredients
        if ing["ingredient_id"] not in existing_ingredient_ids
    ]

    if not unanalyzed_ingredients:
        # Distinguish between "no ingredients meet threshold" vs "all already analyzed"
        if scored_ingredients:
            # All ingredients that meet threshold have already been analyzed
            return {
                "run_id": None,
                "status": "completed",
                "sufficient_data": True,
                "meals_analyzed": meals_count,
                "symptoms_analyzed": symptoms_count,
                "total_ingredients": 0,
                "message": "All ingredients have already been analyzed. Delete individual results to re-analyze them.",
            }
        else:
            # No ingredients met the confidence threshold
            diagnosis_run = DiagnosisRun(
                user_id=MVP_USER_ID,
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

    # Step 4: Create diagnosis run record (only for unanalyzed ingredients)
    diagnosis_run = DiagnosisRun(
        user_id=MVP_USER_ID,
        run_timestamp=datetime.utcnow(),
        status="pending",
        total_ingredients=len(unanalyzed_ingredients),
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
        # Step 5a: Enqueue async tasks (returns immediately)
        queue_service = DiagnosisQueueService(db)
        tasks_enqueued = queue_service.enqueue_diagnosis(
            diagnosis_run=diagnosis_run,
            scored_ingredients=unanalyzed_ingredients,
            web_search_enabled=request.web_search_enabled,
        )

        return {
            "run_id": diagnosis_run.id,
            "status": "processing",
            "sufficient_data": True,
            "meals_analyzed": meals_count,
            "symptoms_analyzed": symptoms_count,
            "total_ingredients": len(unanalyzed_ingredients),
            "message": f"Analysis started. Analyzing {len(unanalyzed_ingredients)} potential trigger ingredients.",
        }
    else:
        # Step 5b: Sync mode (legacy) - run full analysis
        try:
            diagnosis_run = await diagnosis_service.run_diagnosis(
                user_id=MVP_USER_ID,
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
    db: Session = Depends(get_db),
):
    """
    Show diagnosis results page.

    If sufficient data exists, shows latest diagnosis results.
    If a run is in progress, shows progress UI with SSE connection.
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

    # Check if new data is available for analysis
    has_new_data = False
    diagnosis_service = DiagnosisService(db)
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=90)

    # Only check for new data if the run is completed (not still processing)
    if latest_run.status == "completed" and latest_run.sufficient_data:
        # Get existing analyzed ingredient IDs from all completed runs
        existing_ingredient_ids = set(
            row[0] for row in db.query(DiagnosisResult.ingredient_id)
            .join(DiagnosisRun)
            .filter(
                DiagnosisRun.user_id == MVP_USER_ID,
                DiagnosisRun.status == "completed"
            )
            .distinct()
            .all()
        )

        # Run fast SQL checks (no AI calls)
        correlations = diagnosis_service.get_temporal_correlations(MVP_USER_ID, start_date, end_date)
        if correlations:
            aggregated = diagnosis_service.aggregate_correlations_by_ingredient(correlations)
            # Check if any UNANALYZED ingredient meets threshold
            for key, data in aggregated.items():
                ingredient_id = data["ingredient_id"]
                if ingredient_id in existing_ingredient_ids:
                    continue  # Skip already analyzed

                confidence_score, confidence_level = diagnosis_service.calculate_confidence(
                    times_eaten=data["times_eaten"],
                    symptom_occurrences=data["total_symptom_occurrences"],
                    immediate_count=data["immediate_total"],
                    delayed_count=data["delayed_total"],
                    cumulative_count=data["cumulative_total"],
                    avg_severity=sum(s["severity_avg"] for s in data["associated_symptoms"]) / len(data["associated_symptoms"]) if data["associated_symptoms"] else 0,
                )
                if confidence_level != "insufficient_data":
                    has_new_data = True
                    break

    # Aggregate results from all completed runs - get most recent result per ingredient
    # Subquery to find the max result ID per ingredient (most recent)
    max_result_subq = (
        db.query(
            DiagnosisResult.ingredient_id,
            func.max(DiagnosisResult.id).label("max_id")
        )
        .join(DiagnosisRun)
        .filter(
            DiagnosisRun.user_id == MVP_USER_ID,
            DiagnosisRun.status == "completed"
        )
        .group_by(DiagnosisResult.ingredient_id)
        .subquery()
    )

    # Get the actual results matching those max IDs
    all_results = (
        db.query(DiagnosisResult)
        .join(max_result_subq, DiagnosisResult.id == max_result_subq.c.max_id)
        .options(
            joinedload(DiagnosisResult.ingredient),
            joinedload(DiagnosisResult.citations),
            joinedload(DiagnosisResult.feedback),
        )
        .order_by(DiagnosisResult.confidence_score.desc())
        .all()
    )

    # Show results page with run_id for SSE streaming
    return templates.TemplateResponse(
        "diagnosis/results.html",
        {
            "request": request,
            "diagnosis_run": latest_run,
            "results": all_results,
            "run_id": latest_run.id,
            "run_status": latest_run.status,
            "total_ingredients": latest_run.total_ingredients,
            "completed_ingredients": latest_run.completed_ingredients,
            "has_new_data": has_new_data,
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
