"""
Unit tests for AIUsageService.

Tests the AI usage tracking functionality including:
- Cost calculation
- Usage logging
- Cost aggregation
"""

from decimal import Decimal
from sqlalchemy.orm import Session

from app.services.ai_usage_service import AIUsageService
from tests.factories import create_user


class TestCostCalculation:
    """Tests for cost calculation."""

    def test_calculate_cost_sonnet_model(self, db: Session):
        """Test cost calculation for Sonnet model."""
        service = AIUsageService(db)

        cost = service.calculate_cost_cents(
            model="claude-sonnet-4-5-20250929",
            input_tokens=1000,
            output_tokens=500,
            cached_tokens=0,
        )

        # Should be a positive decimal
        assert cost > 0
        assert isinstance(cost, Decimal)

    def test_calculate_cost_non_sonnet_model(self, db: Session):
        """Test cost calculation for non-Sonnet model (defaults to Sonnet pricing)."""
        service = AIUsageService(db)

        cost = service.calculate_cost_cents(
            model="claude-haiku-3",
            input_tokens=1000,
            output_tokens=500,
            cached_tokens=0,
        )

        # Should still calculate (defaults to Sonnet pricing)
        assert cost > 0

    def test_calculate_cost_with_cached_tokens(self, db: Session):
        """Test that cached tokens are charged at reduced rate."""
        service = AIUsageService(db)

        # Calculate cost without caching
        cost_no_cache = service.calculate_cost_cents(
            model="claude-sonnet-4-5-20250929",
            input_tokens=1000,
            output_tokens=500,
            cached_tokens=0,
        )

        # Calculate cost with same tokens but half cached
        cost_with_cache = service.calculate_cost_cents(
            model="claude-sonnet-4-5-20250929",
            input_tokens=1000,
            output_tokens=500,
            cached_tokens=500,  # Half cached at 10% rate
        )

        # Cached should be cheaper
        assert cost_with_cache < cost_no_cache

    def test_calculate_cost_zero_tokens(self, db: Session):
        """Test cost calculation with zero tokens."""
        service = AIUsageService(db)

        cost = service.calculate_cost_cents(
            model="claude-sonnet-4-5-20250929",
            input_tokens=0,
            output_tokens=0,
            cached_tokens=0,
        )

        assert cost == Decimal("0")


class TestUsageLogging:
    """Tests for usage logging."""

    def test_log_usage_basic(self, db: Session):
        """Test basic usage logging."""
        user = create_user(db)
        service = AIUsageService(db)

        log_entry = service.log_usage(
            service_type="meal_analysis",
            model="claude-sonnet-4-5-20250929",
            input_tokens=1000,
            output_tokens=500,
            user_id=str(user.id),
        )

        assert log_entry.id is not None
        assert log_entry.service_type == "meal_analysis"
        assert log_entry.input_tokens == 1000
        assert log_entry.output_tokens == 500
        assert log_entry.estimated_cost_cents > 0

    def test_log_usage_with_all_params(self, db: Session):
        """Test usage logging with all optional parameters."""
        user = create_user(db)
        service = AIUsageService(db)

        log_entry = service.log_usage(
            service_type="diagnosis",
            model="claude-sonnet-4-5-20250929",
            input_tokens=2000,
            output_tokens=1000,
            cached_tokens=500,
            user_id=str(user.id),
            request_id="12345",
            request_type="diagnosis_run",
            web_search_enabled=True,
            success=True,
            error_message=None,
        )

        assert log_entry.cached_tokens == 500
        assert log_entry.request_id == "12345"
        assert log_entry.request_type == "diagnosis_run"
        assert log_entry.web_search_enabled is True
        assert log_entry.success is True

    def test_log_usage_failed_request(self, db: Session):
        """Test logging a failed request."""
        service = AIUsageService(db)

        log_entry = service.log_usage(
            service_type="meal_analysis",
            model="claude-sonnet-4-5-20250929",
            input_tokens=500,
            output_tokens=0,
            success=False,
            error_message="API timeout",
        )

        assert log_entry.success is False
        assert log_entry.error_message == "API timeout"


class TestCostAggregation:
    """Tests for cost aggregation."""

    def test_get_total_cost_for_run(self, db: Session):
        """Test getting total cost for a diagnosis run."""
        service = AIUsageService(db)

        # Create some log entries for the same run
        for i in range(3):
            service.log_usage(
                service_type="diagnosis",
                model="claude-sonnet-4-5-20250929",
                input_tokens=1000,
                output_tokens=500,
                request_id="42",
                request_type="diagnosis_run",
            )

        total = service.get_total_cost_for_run(42)

        # Should be sum of all 3 entries
        assert total > 0

    def test_get_total_cost_for_run_no_logs(self, db: Session):
        """Test getting total cost when no logs exist."""
        service = AIUsageService(db)

        total = service.get_total_cost_for_run(99999)

        assert total == Decimal("0")


class TestUsageSummary:
    """Tests for usage summary."""

    def test_get_usage_summary_no_filter(self, db: Session):
        """Test getting usage summary without user filter."""
        user = create_user(db)
        service = AIUsageService(db)

        # Create some usage logs
        for i in range(5):
            service.log_usage(
                service_type="test",
                model="claude-sonnet-4-5-20250929",
                input_tokens=100,
                output_tokens=50,
                user_id=str(user.id),
            )

        summary = service.get_usage_summary()

        assert summary["total_calls"] >= 5
        assert summary["total_input_tokens"] >= 500
        assert summary["period_days"] == 30

    def test_get_usage_summary_with_user_filter(self, db: Session):
        """Test getting usage summary filtered by user."""
        user1 = create_user(db, email="user1@example.com")
        user2 = create_user(db, email="user2@example.com")
        service = AIUsageService(db)

        # Create logs for user1
        for i in range(3):
            service.log_usage(
                service_type="test",
                model="claude-sonnet-4-5-20250929",
                input_tokens=100,
                output_tokens=50,
                user_id=str(user1.id),
            )

        # Create logs for user2
        for i in range(2):
            service.log_usage(
                service_type="test",
                model="claude-sonnet-4-5-20250929",
                input_tokens=200,
                output_tokens=100,
                user_id=str(user2.id),
            )

        # Get summary for user1 only
        summary = service.get_usage_summary(user_id=str(user1.id))

        assert summary["total_calls"] == 3
        assert summary["total_input_tokens"] == 300

    def test_get_usage_summary_custom_days(self, db: Session):
        """Test usage summary with custom day range."""
        service = AIUsageService(db)

        summary = service.get_usage_summary(days=7)

        assert summary["period_days"] == 7

    def test_get_usage_summary_empty(self, db: Session):
        """Test usage summary when no logs exist for a user."""
        import uuid

        # Use a valid UUID that has no logs
        service = AIUsageService(db)

        summary = service.get_usage_summary(user_id=str(uuid.uuid4()))

        assert summary["total_calls"] == 0
        assert summary["total_input_tokens"] == 0
        assert summary["total_cost_cents"] == 0.0
        assert summary["total_cost_dollars"] == 0.0
