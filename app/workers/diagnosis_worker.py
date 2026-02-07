"""
Dramatiq worker for async per-ingredient diagnosis analysis.

This worker handles individual ingredient analysis tasks, allowing
parallel processing and real-time progress updates via SSE.
"""
import dramatiq
from dramatiq.middleware import CurrentMessage
from datetime import datetime
import asyncio
import json

# Import broker setup (must be before actor definitions)
from app.workers import redis_broker
from app.database import SessionLocal
from app.models import DiagnosisRun, DiagnosisResult, DiagnosisCitation
from app.services.sse_publisher import SSEPublisher
from app.services.ai_usage_service import AIUsageService


def run_async(coro):
    """Helper to run async code in sync context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@dramatiq.actor(max_retries=2, min_backoff=5000, max_backoff=60000)
def analyze_ingredient(
    run_id: int,
    ingredient_data: dict,
    user_meal_history: list,
    web_search_enabled: bool = True
):
    """
    Analyze a single ingredient for symptom correlations.

    This actor:
    1. Calls Claude API for single-ingredient analysis
    2. Stores DiagnosisResult + citations in database
    3. Logs AI usage for cost tracking
    4. Increments completed_ingredients counter
    5. Publishes SSE event via Redis pub/sub

    Args:
        run_id: DiagnosisRun ID to attach results to
        ingredient_data: Dict with ingredient stats and correlation data
        user_meal_history: List of user's recent meals for context
        web_search_enabled: Whether to enable web search for medical grounding
    """
    from app.services.ai_service import ClaudeService, ServiceUnavailableError, RateLimitError

    db = SessionLocal()
    sse_publisher = SSEPublisher()
    ai_usage_service = AIUsageService(db)

    try:
        # Get diagnosis run
        diagnosis_run = db.query(DiagnosisRun).filter(DiagnosisRun.id == run_id).first()
        if not diagnosis_run:
            raise ValueError(f"DiagnosisRun {run_id} not found")

        ingredient_name = ingredient_data.get("ingredient_name", "unknown")

        # Call Claude API for single-ingredient analysis
        claude_service = ClaudeService()

        try:
            result = run_async(claude_service.diagnose_single_ingredient(
                ingredient_data=ingredient_data,
                user_meal_history=user_meal_history,
                web_search_enabled=web_search_enabled
            ))
        except ServiceUnavailableError as e:
            # Log failure and publish error
            ai_usage_service.log_usage(
                service_type="diagnosis_ingredient",
                model=claude_service.sonnet_model,
                input_tokens=0,
                output_tokens=0,
                cached_tokens=0,
                request_id=str(run_id),
                request_type="diagnosis_run",
                web_search_enabled=web_search_enabled,
                success=False,
                error_message=str(e)
            )
            sse_publisher.publish_error(run_id, f"Failed to analyze {ingredient_name}: {str(e)}")
            raise
        except RateLimitError as e:
            sse_publisher.publish_error(run_id, "Rate limit exceeded. Please wait and try again.")
            raise

        # Log AI usage
        usage_stats = result.get("usage_stats", {})
        ai_usage_service.log_usage(
            service_type="diagnosis_ingredient",
            model=claude_service.sonnet_model,
            input_tokens=usage_stats.get("input_tokens", 0),
            output_tokens=usage_stats.get("output_tokens", 0),
            cached_tokens=usage_stats.get("cached_tokens", 0),
            request_id=str(run_id),
            request_type="diagnosis_run",
            web_search_enabled=web_search_enabled,
            success=True
        )

        # Create DiagnosisResult record
        diagnosis_result = DiagnosisResult(
            run_id=run_id,
            ingredient_id=ingredient_data["ingredient_id"],
            confidence_score=ingredient_data["confidence_score"],
            confidence_level=ingredient_data["confidence_level"],
            immediate_correlation=ingredient_data.get("immediate_total", 0),
            delayed_correlation=ingredient_data.get("delayed_total", 0),
            cumulative_correlation=ingredient_data.get("cumulative_total", 0),
            times_eaten=ingredient_data["times_eaten"],
            times_followed_by_symptoms=ingredient_data["total_symptom_occurrences"],
            state_matters=False,
            problematic_states=[ingredient_data.get("state")] if ingredient_data.get("state") else None,
            associated_symptoms=ingredient_data["associated_symptoms"],
            # Structured summaries from AI
            diagnosis_summary=result.get("diagnosis_summary"),
            recommendations_summary=result.get("recommendations_summary"),
            processing_suggestions=result.get("processing_suggestions"),
            alternative_meals=result.get("alternative_meals"),
            # Legacy ai_analysis field for backwards compatibility
            ai_analysis=result.get("diagnosis_summary", "") + "\n\n" + result.get("recommendations_summary", "")
        )
        db.add(diagnosis_result)
        db.flush()

        # Create citations
        for citation in result.get("citations", []):
            citation_obj = DiagnosisCitation(
                result_id=diagnosis_result.id,
                source_url=citation.get("url", ""),
                source_title=citation.get("title", ""),
                source_type=citation.get("source_type", "other"),
                snippet=citation.get("snippet", ""),
                relevance_score=citation.get("relevance", 0.0)
            )
            db.add(citation_obj)

        # Increment completed count atomically to avoid race conditions with parallel workers
        from sqlalchemy import text
        db.execute(
            text("UPDATE diagnosis_runs SET completed_ingredients = completed_ingredients + 1 WHERE id = :run_id"),
            {"run_id": run_id}
        )
        db.commit()

        # Refresh to get updated count
        db.refresh(diagnosis_run)

        # Publish SSE progress event
        sse_publisher.publish_progress(
            run_id=run_id,
            completed=diagnosis_run.completed_ingredients,
            total=diagnosis_run.total_ingredients or 0,
            ingredient=ingredient_name
        )

        # Publish SSE result event
        result_dict = {
            "id": diagnosis_result.id,
            "ingredient_id": diagnosis_result.ingredient_id,
            "ingredient_name": ingredient_name,
            "confidence_score": float(diagnosis_result.confidence_score),
            "confidence_level": diagnosis_result.confidence_level,
            "diagnosis_summary": diagnosis_result.diagnosis_summary,
            "recommendations_summary": diagnosis_result.recommendations_summary,
            "processing_suggestions": diagnosis_result.processing_suggestions,
            "alternative_meals": diagnosis_result.alternative_meals,
            "associated_symptoms": diagnosis_result.associated_symptoms,
            "times_eaten": diagnosis_result.times_eaten,
            "times_followed_by_symptoms": diagnosis_result.times_followed_by_symptoms,
            "citations": [
                {
                    "url": c.get("url"),
                    "title": c.get("title"),
                    "source_type": c.get("source_type"),
                    "snippet": c.get("snippet")
                }
                for c in result.get("citations", [])
            ]
        }
        sse_publisher.publish_result(run_id, result_dict)

        # Check if this was the last ingredient - finalize immediately if so
        if diagnosis_run.completed_ingredients >= (diagnosis_run.total_ingredients or 0):
            diagnosis_run.status = "completed"
            diagnosis_run.completed_at = datetime.utcnow()
            db.commit()

            # Count total results and publish completion
            total_results = len(diagnosis_run.results) if diagnosis_run.results else 0
            sse_publisher.publish_complete(run_id, total_results)

    except Exception as e:
        db.rollback()
        # Publish error event
        sse_publisher.publish_error(run_id, str(e))
        raise
    finally:
        db.close()
        sse_publisher.close()


@dramatiq.actor
def finalize_diagnosis_run(run_id: int):
    """
    Finalize a diagnosis run after all ingredients have been analyzed.

    Sets status to 'completed' and publishes final SSE event.

    Args:
        run_id: DiagnosisRun ID to finalize
    """
    db = SessionLocal()
    sse_publisher = SSEPublisher()

    try:
        diagnosis_run = db.query(DiagnosisRun).filter(DiagnosisRun.id == run_id).first()
        if not diagnosis_run:
            raise ValueError(f"DiagnosisRun {run_id} not found")

        # Skip if already completed (may have been finalized by last worker)
        if diagnosis_run.status == "completed":
            return

        # Update status
        diagnosis_run.status = "completed"
        diagnosis_run.completed_at = datetime.utcnow()
        db.commit()

        # Count total results
        total_results = len(diagnosis_run.results) if diagnosis_run.results else 0

        # Publish completion event
        sse_publisher.publish_complete(run_id, total_results)

    except Exception as e:
        db.rollback()
        # Mark as failed
        try:
            diagnosis_run = db.query(DiagnosisRun).filter(DiagnosisRun.id == run_id).first()
            if diagnosis_run:
                diagnosis_run.status = "failed"
                diagnosis_run.error_message = str(e)
                diagnosis_run.completed_at = datetime.utcnow()
                db.commit()
        except:
            pass
        sse_publisher.publish_error(run_id, str(e))
        raise
    finally:
        db.close()
        sse_publisher.close()
