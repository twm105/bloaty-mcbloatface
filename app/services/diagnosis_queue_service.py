"""
Service for enqueuing diagnosis tasks via Dramatiq.

Handles the orchestration of per-ingredient analysis tasks,
including task creation, grouping, and completion callbacks.
"""

from datetime import datetime
from typing import List, Dict
from sqlalchemy.orm import Session

from app.models import DiagnosisRun, Meal
from app.workers.diagnosis_worker import analyze_ingredient, finalize_diagnosis_run


class DiagnosisQueueService:
    """Orchestrates async diagnosis task queuing via Dramatiq."""

    def __init__(self, db: Session):
        self.db = db

    def enqueue_diagnosis(
        self,
        diagnosis_run: DiagnosisRun,
        scored_ingredients: List[Dict],
        web_search_enabled: bool = True,
    ) -> int:
        """
        Enqueue per-ingredient analysis tasks.

        Creates Dramatiq tasks for each ingredient, sets up completion
        callback, and updates diagnosis run status.

        Args:
            diagnosis_run: The DiagnosisRun record to attach results to
            scored_ingredients: List of ingredient data with confidence scores
            web_search_enabled: Whether to enable web search

        Returns:
            Number of tasks enqueued
        """
        if not scored_ingredients:
            return 0

        # Update run status
        diagnosis_run.status = "processing"
        diagnosis_run.started_at = datetime.utcnow()
        diagnosis_run.total_ingredients = len(scored_ingredients)
        diagnosis_run.completed_ingredients = 0
        self.db.commit()

        # Get user's meal history for context (last 20 meals)
        user_meal_history = self._get_user_meal_history(diagnosis_run.user_id, limit=20)

        # Enqueue analysis tasks for each ingredient
        messages = []
        for ingredient_data in scored_ingredients:
            msg = analyze_ingredient.send(
                run_id=diagnosis_run.id,
                ingredient_data=ingredient_data,
                user_meal_history=user_meal_history,
                web_search_enabled=web_search_enabled,
            )
            messages.append(msg)

        # Schedule finalization after all tasks complete
        # Using a simple approach: enqueue finalize with delay
        # In production, use Dramatiq groups/pipelines for proper completion handling
        finalize_diagnosis_run.send_with_options(
            args=(diagnosis_run.id,),
            delay=len(scored_ingredients) * 30000,  # Estimate 30s per ingredient
        )

        return len(messages)

    def _get_user_meal_history(self, user_id: str, limit: int = 20) -> List[Dict]:
        """
        Get recent meal history for context in AI analysis.

        Returns simplified meal data for the AI to reference when
        suggesting alternative meals.

        Args:
            user_id: User ID
            limit: Maximum number of meals to return

        Returns:
            List of dicts with meal info: {id, name, timestamp, ingredients}
        """
        meals = (
            self.db.query(Meal)
            .filter(Meal.user_id == user_id, Meal.status == "published")
            .order_by(Meal.timestamp.desc())
            .limit(limit)
            .all()
        )

        result = []
        for meal in meals:
            ingredients = []
            for mi in meal.meal_ingredients:
                if mi.ingredient:
                    ingredients.append(
                        {
                            "name": mi.ingredient.normalized_name,
                            "state": mi.state.value if mi.state else None,
                        }
                    )

            result.append(
                {
                    "id": meal.id,
                    "name": meal.name or "Untitled Meal",
                    "timestamp": meal.timestamp.isoformat() if meal.timestamp else None,
                    "ingredients": ingredients,
                }
            )

        return result

    def get_run_status(self, run_id: int) -> Dict:
        """
        Get current status of a diagnosis run.

        Args:
            run_id: DiagnosisRun ID

        Returns:
            Dict with status info
        """
        run = self.db.query(DiagnosisRun).filter(DiagnosisRun.id == run_id).first()
        if not run:
            return {"error": "Run not found"}

        return {
            "run_id": run.id,
            "status": run.status,
            "total_ingredients": run.total_ingredients,
            "completed_ingredients": run.completed_ingredients,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "error_message": run.error_message,
        }
