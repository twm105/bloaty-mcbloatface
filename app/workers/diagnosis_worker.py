"""
Dramatiq worker for async per-ingredient diagnosis analysis.

This worker handles individual ingredient analysis tasks, allowing
parallel processing and real-time progress updates via SSE.
"""

import dramatiq
from datetime import datetime
import asyncio

# Import broker setup (must be before actor definitions)
from app.database import SessionLocal
from app.models import (
    DiagnosisRun,
    DiagnosisResult,
    DiagnosisCitation,
    DiscountedIngredient,
)
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
    web_search_enabled: bool = True,
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
    from app.services.ai_service import (
        ClaudeService,
        ServiceUnavailableError,
        RateLimitError,
    )

    db = SessionLocal()
    sse_publisher = SSEPublisher()
    ai_usage_service = AIUsageService(db)

    try:
        # Get diagnosis run
        diagnosis_run = db.query(DiagnosisRun).filter(DiagnosisRun.id == run_id).first()
        if not diagnosis_run:
            raise ValueError(f"DiagnosisRun {run_id} not found")

        ingredient_name = ingredient_data.get("ingredient_name", "unknown")
        cooccurrence_data = ingredient_data.get("cooccurrence", [])

        claude_service = ClaudeService()

        # =====================================================================
        # PIPELINE: research → classify → adapt_to_plain_english
        #
        # Step 1: Medical research (web search + technical assessment)
        # Step 2: Classify root cause (with research context, no web search)
        # Step 3: If kept, adapt to plain English (no web search)
        # =====================================================================

        # Step 1: Medical research — technical assessment with web search
        research = None
        try:
            research = run_async(
                claude_service.research_ingredient(
                    ingredient_data=ingredient_data,
                    web_search_enabled=web_search_enabled,
                )
            )
            # Log research AI usage
            research_usage = research.get("usage_stats", {})
            ai_usage_service.log_usage(
                service_type="diagnosis_research",
                model=claude_service.sonnet_model,
                input_tokens=research_usage.get("input_tokens", 0),
                output_tokens=research_usage.get("output_tokens", 0),
                cached_tokens=research_usage.get("cached_tokens", 0),
                request_id=str(run_id),
                request_type="diagnosis_run",
                web_search_enabled=web_search_enabled,
                success=True,
            )
        except Exception as e:
            # On research error, proceed without medical context
            print(f"Research error for {ingredient_name}: {e}")
            research = None

        # Step 2: Classify root cause — now informed by medical research
        medical_grounding = ""
        if research:
            medical_grounding = research.get("medical_assessment", "")

        is_confounder = False
        confounder_result = None

        try:
            confounder_result = run_async(
                claude_service.classify_root_cause(
                    ingredient_data=ingredient_data,
                    cooccurrence_data=cooccurrence_data,
                    medical_grounding=medical_grounding,
                    web_search_enabled=False,  # Already searched in step 1
                )
            )
            is_confounder = not confounder_result.get("root_cause", True)
        except Exception as e:
            # On classification error, treat as root cause (don't discard)
            print(f"Root cause classification error for {ingredient_name}: {e}")
            is_confounder = False

        # If confounder, store as DiscountedIngredient and exit early
        if is_confounder and confounder_result:
            # Find confounded_by ingredient ID
            confounded_by_name = confounder_result.get("confounded_by")
            confounded_by_id = None
            if confounded_by_name:
                for cooc in cooccurrence_data:
                    if (
                        cooc.get("with_ingredient_name", "").lower()
                        == confounded_by_name.lower()
                    ):
                        confounded_by_id = cooc.get("with_ingredient_id")
                        break

            # Get first co-occurrence record for stats
            cooc = cooccurrence_data[0] if cooccurrence_data else {}

            discounted = DiscountedIngredient(
                run_id=run_id,
                ingredient_id=ingredient_data["ingredient_id"],
                discard_justification=confounder_result.get(
                    "discard_justification", "Confounded by co-occurring ingredient"
                ),
                confounded_by_ingredient_id=confounded_by_id,
                # Original correlation data
                original_confidence_score=ingredient_data.get("confidence_score"),
                original_confidence_level=ingredient_data.get("confidence_level"),
                times_eaten=ingredient_data.get("times_eaten"),
                times_followed_by_symptoms=ingredient_data.get(
                    "total_symptom_occurrences"
                ),
                immediate_correlation=ingredient_data.get("immediate_total"),
                delayed_correlation=ingredient_data.get("delayed_total"),
                cumulative_correlation=ingredient_data.get("cumulative_total"),
                associated_symptoms=ingredient_data.get("associated_symptoms"),
                # Co-occurrence data
                conditional_probability=cooc.get("conditional_probability"),
                reverse_probability=cooc.get("reverse_probability"),
                lift=cooc.get("lift"),
                cooccurrence_meals_count=cooc.get("cooccurrence_meals"),
                # Medical grounding
                medical_grounding_summary=confounder_result.get("medical_reasoning"),
            )
            db.add(discounted)

            # Increment completed count
            from sqlalchemy import text

            db.execute(
                text(
                    "UPDATE diagnosis_runs SET completed_ingredients = completed_ingredients + 1 WHERE id = :run_id"
                ),
                {"run_id": run_id},
            )
            db.commit()
            db.refresh(diagnosis_run)

            # Publish SSE progress (ingredient analyzed but discounted)
            sse_publisher.publish_progress(
                run_id=run_id,
                completed=diagnosis_run.completed_ingredients,
                total=diagnosis_run.total_ingredients or 0,
                ingredient=f"{ingredient_name} (discounted)",
            )

            # Publish discounted ingredient data for real-time UI update
            sse_publisher.publish_discounted(
                run_id,
                {
                    "id": discounted.id,
                    "ingredient_id": discounted.ingredient_id,
                    "ingredient_name": ingredient_name,
                    "discard_justification": discounted.discard_justification,
                    "confounded_by_name": confounded_by_name,
                    "original_confidence_level": discounted.original_confidence_level,
                    "times_eaten": discounted.times_eaten,
                    "times_followed_by_symptoms": discounted.times_followed_by_symptoms,
                    "medical_grounding_summary": discounted.medical_grounding_summary,
                },
            )

            # Check if this was the last ingredient
            if diagnosis_run.completed_ingredients >= (
                diagnosis_run.total_ingredients or 0
            ):
                diagnosis_run.status = "completed"
                diagnosis_run.completed_at = datetime.utcnow()
                db.commit()
                total_results = (
                    len(diagnosis_run.results) if diagnosis_run.results else 0
                )
                sse_publisher.publish_complete(run_id, total_results)

            return  # Exit early - don't do full analysis for confounders

        # Step 3: Adapt to plain English — uses research, no web search
        try:
            result = run_async(
                claude_service.adapt_to_plain_english(
                    ingredient_data=ingredient_data,
                    medical_research=research or {},
                    user_meal_history=user_meal_history,
                )
            )
        except ServiceUnavailableError as e:
            ai_usage_service.log_usage(
                service_type="diagnosis_ingredient",
                model=claude_service.sonnet_model,
                input_tokens=0,
                output_tokens=0,
                cached_tokens=0,
                request_id=str(run_id),
                request_type="diagnosis_run",
                web_search_enabled=False,
                success=False,
                error_message=str(e),
            )
            sse_publisher.publish_error(
                run_id, f"Failed to analyze {ingredient_name}: {str(e)}"
            )
            raise
        except RateLimitError:
            sse_publisher.publish_error(
                run_id, "Rate limit exceeded. Please wait and try again."
            )
            raise

        # Log AI usage for the adapt step
        usage_stats = result.get("usage_stats", {})
        ai_usage_service.log_usage(
            service_type="diagnosis_ingredient",
            model=claude_service.sonnet_model,
            input_tokens=usage_stats.get("input_tokens", 0),
            output_tokens=usage_stats.get("output_tokens", 0),
            cached_tokens=usage_stats.get("cached_tokens", 0),
            request_id=str(run_id),
            request_type="diagnosis_run",
            web_search_enabled=False,
            success=True,
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
            problematic_states=[ingredient_data.get("state")]
            if ingredient_data.get("state")
            else None,
            associated_symptoms=ingredient_data["associated_symptoms"],
            # Structured summaries from AI
            diagnosis_summary=result.get("diagnosis_summary"),
            recommendations_summary=result.get("recommendations_summary"),
            processing_suggestions=result.get("processing_suggestions"),
            alternative_meals=result.get("alternative_meals"),
            # Legacy ai_analysis field for backwards compatibility
            ai_analysis=result.get("diagnosis_summary", "")
            + "\n\n"
            + result.get("recommendations_summary", ""),
        )
        db.add(diagnosis_result)
        db.flush()

        # Create citations — merge from research + adapt steps
        all_citations = []
        if research:
            all_citations.extend(research.get("citations", []))
        all_citations.extend(result.get("citations", []))

        # Deduplicate by URL
        seen_urls = set()
        for citation in all_citations:
            url = citation.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                citation_obj = DiagnosisCitation(
                    result_id=diagnosis_result.id,
                    source_url=url,
                    source_title=citation.get("title", ""),
                    source_type=citation.get("source_type", "other"),
                    snippet=citation.get("snippet", ""),
                    relevance_score=citation.get("relevance", 0.0),
                )
                db.add(citation_obj)

        # Increment completed count atomically to avoid race conditions with parallel workers
        from sqlalchemy import text

        db.execute(
            text(
                "UPDATE diagnosis_runs SET completed_ingredients = completed_ingredients + 1 WHERE id = :run_id"
            ),
            {"run_id": run_id},
        )
        db.commit()

        # Refresh to get updated count
        db.refresh(diagnosis_run)

        # Publish SSE progress event
        sse_publisher.publish_progress(
            run_id=run_id,
            completed=diagnosis_run.completed_ingredients,
            total=diagnosis_run.total_ingredients or 0,
            ingredient=ingredient_name,
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
                    "url": c.get("url", ""),
                    "title": c.get("title", ""),
                    "source_type": c.get("source_type", ""),
                    "snippet": c.get("snippet", ""),
                }
                for c in all_citations
                if c.get("url")
            ],
        }
        sse_publisher.publish_result(run_id, result_dict)

        # Check if this was the last ingredient - finalize immediately if so
        if diagnosis_run.completed_ingredients >= (
            diagnosis_run.total_ingredients or 0
        ):
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
            diagnosis_run = (
                db.query(DiagnosisRun).filter(DiagnosisRun.id == run_id).first()
            )
            if diagnosis_run:
                diagnosis_run.status = "failed"
                diagnosis_run.error_message = str(e)
                diagnosis_run.completed_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass
        sse_publisher.publish_error(run_id, str(e))
        raise
    finally:
        db.close()
        sse_publisher.close()
