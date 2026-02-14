"""
AI Usage tracking service for monitoring API costs.

Logs all AI API calls with token usage and calculates estimated costs.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AIUsageLog


class AIUsageService:
    """Service for logging and calculating AI API usage costs."""

    def __init__(self, db: Session):
        self.db = db

    def calculate_cost_cents(
        self, model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0
    ) -> Decimal:
        """
        Calculate estimated cost in cents for an API call.

        Uses model-specific pricing from settings.
        Cached tokens are charged at 10% of the normal rate.

        Args:
            model: Model name (e.g., 'claude-sonnet-4-5-20250929')
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cached_tokens: Number of cached input tokens (already included in input_tokens)

        Returns:
            Estimated cost in cents
        """
        # Determine pricing based on model
        if "sonnet" in model.lower():
            input_cost = settings.sonnet_input_cost_per_1k
            output_cost = settings.sonnet_output_cost_per_1k
        else:
            # Default to Sonnet pricing
            input_cost = settings.sonnet_input_cost_per_1k
            output_cost = settings.sonnet_output_cost_per_1k

        # Calculate costs
        # Non-cached input tokens charged at full rate
        non_cached_input = input_tokens - cached_tokens
        # Cached tokens charged at 10% rate
        cached_cost = (cached_tokens / 1000) * input_cost * 0.1
        non_cached_cost = (non_cached_input / 1000) * input_cost
        output_cost_total = (output_tokens / 1000) * output_cost

        total_cost = cached_cost + non_cached_cost + output_cost_total

        return Decimal(str(round(total_cost, 4)))

    def log_usage(
        self,
        service_type: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        request_type: Optional[str] = None,
        web_search_enabled: bool = False,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> AIUsageLog:
        """
        Log an AI API usage event.

        Args:
            service_type: Type of service ('meal_analysis', 'diagnosis', etc.)
            model: Model name used
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cached_tokens: Number of cached input tokens
            user_id: Optional user ID
            request_id: Optional request ID for linking (e.g., diagnosis_run.id)
            request_type: Optional request type ('diagnosis_run', 'meal', etc.)
            web_search_enabled: Whether web search was enabled
            success: Whether the call succeeded
            error_message: Error message if failed

        Returns:
            Created AIUsageLog record
        """
        cost_cents = self.calculate_cost_cents(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
        )

        log_entry = AIUsageLog(
            user_id=user_id,
            timestamp=datetime.utcnow(),
            service_type=service_type,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            estimated_cost_cents=cost_cents,
            request_id=request_id,
            request_type=request_type,
            web_search_enabled=web_search_enabled,
            success=success,
            error_message=error_message,
        )

        self.db.add(log_entry)
        self.db.commit()
        self.db.refresh(log_entry)

        return log_entry

    def get_total_cost_for_run(self, run_id: int) -> Decimal:
        """
        Get total cost for a diagnosis run.

        Args:
            run_id: DiagnosisRun ID

        Returns:
            Total cost in cents
        """
        from sqlalchemy import func

        result = (
            self.db.query(func.sum(AIUsageLog.estimated_cost_cents))
            .filter(
                AIUsageLog.request_id == str(run_id),
                AIUsageLog.request_type == "diagnosis_run",
            )
            .scalar()
        )

        return result or Decimal("0")

    def get_usage_summary(self, user_id: Optional[str] = None, days: int = 30) -> dict:
        """
        Get usage summary for a user over the past N days.

        Args:
            user_id: Optional user ID to filter by
            days: Number of days to look back

        Returns:
            Dict with usage statistics
        """
        from sqlalchemy import func
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(days=days)

        query = self.db.query(
            func.count(AIUsageLog.id).label("total_calls"),
            func.sum(AIUsageLog.input_tokens).label("total_input_tokens"),
            func.sum(AIUsageLog.output_tokens).label("total_output_tokens"),
            func.sum(AIUsageLog.cached_tokens).label("total_cached_tokens"),
            func.sum(AIUsageLog.estimated_cost_cents).label("total_cost_cents"),
        ).filter(AIUsageLog.timestamp >= cutoff)

        if user_id:
            query = query.filter(AIUsageLog.user_id == user_id)

        result = query.first()

        return {
            "total_calls": result.total_calls or 0,
            "total_input_tokens": result.total_input_tokens or 0,
            "total_output_tokens": result.total_output_tokens or 0,
            "total_cached_tokens": result.total_cached_tokens or 0,
            "total_cost_cents": float(result.total_cost_cents or 0),
            "total_cost_dollars": round(float(result.total_cost_cents or 0) / 100, 2),
            "period_days": days,
        }
