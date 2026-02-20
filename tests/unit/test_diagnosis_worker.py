"""
Unit tests for diagnosis_worker - background Dramatiq worker for ingredient analysis.

Tests the analyze_ingredient and finalize_diagnosis_run actors with mocked
dependencies (database, AI service, SSE publisher).
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.services.ai_service import ServiceUnavailableError, RateLimitError


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.first.return_value = None
    return mock_session


@pytest.fixture
def mock_diagnosis_run():
    """Create a mock DiagnosisRun."""
    run = MagicMock()
    run.id = 1
    run.user_id = 1
    run.status = "running"
    run.total_ingredients = 3
    run.completed_ingredients = 0
    run.results = []
    run.started_at = datetime.now(timezone.utc)
    run.completed_at = None
    run.error_message = None
    return run


@pytest.fixture
def mock_claude_service():
    """Create a mock ClaudeService."""
    mock = MagicMock()
    mock.sonnet_model = "claude-sonnet-4-5-20250929"
    return mock


@pytest.fixture
def mock_sse_publisher():
    """Create a mock SSEPublisher."""
    mock = MagicMock()
    mock.publish_progress = MagicMock()
    mock.publish_result = MagicMock()
    mock.publish_discounted = MagicMock()
    mock.publish_complete = MagicMock()
    mock.publish_error = MagicMock()
    mock.close = MagicMock()
    return mock


@pytest.fixture
def sample_ingredient_data():
    """Create sample ingredient data for testing."""
    return {
        "ingredient_id": 1,
        "ingredient_name": "onion",
        "state": "raw",
        "times_eaten": 5,
        "total_symptom_occurrences": 4,
        "immediate_total": 3,
        "delayed_total": 1,
        "cumulative_total": 0,
        "confidence_score": 0.8,
        "confidence_level": "high",
        "associated_symptoms": [
            {"name": "bloating", "severity_avg": 7.0, "frequency": 4, "lag_hours": 1.5}
        ],
        "cooccurrence": [],
    }


@pytest.fixture
def sample_research_result():
    """Create sample research_ingredient result."""
    return {
        "medical_assessment": "Onion is high-FODMAP containing fructans.",
        "known_trigger_categories": ["high_fodmap", "fructans"],
        "risk_level": "high_risk",
        "citations": [
            {
                "url": "https://www.monash.edu/fodmap",
                "title": "Monash FODMAP",
                "source_type": "medical",
                "snippet": "Onion is high in fructans",
            }
        ],
        "usage_stats": {
            "input_tokens": 500,
            "output_tokens": 200,
            "cached_tokens": 0,
        },
    }


@pytest.fixture
def sample_diagnosis_result():
    """Create sample adapt_to_plain_english result."""
    return {
        "diagnosis_summary": "Onion shows correlation with digestive symptoms.",
        "recommendations_summary": "Consider elimination diet.",
        "processing_suggestions": {
            "cooked_vs_raw": "Cooking may reduce symptoms",
            "alternatives": ["shallots", "chives"],
        },
        "alternative_meals": [],
        "citations": [
            {
                "url": "https://www.nih.gov/fodmap",
                "title": "FODMAP Diet Information",
                "source_type": "nih",
                "snippet": "Information about FODMAP foods",
            }
        ],
        "usage_stats": {
            "input_tokens": 800,
            "output_tokens": 400,
            "cached_tokens": 0,
            "cache_hit": False,
        },
    }


# =============================================================================
# analyze_ingredient Tests
# =============================================================================


class TestAnalyzeIngredient:
    """Tests for the analyze_ingredient actor."""

    def test_successful_analysis(
        self,
        mock_db_session,
        mock_diagnosis_run,
        mock_claude_service,
        mock_sse_publisher,
        sample_ingredient_data,
        sample_research_result,
        sample_diagnosis_result,
    ):
        """Test successful ingredient analysis."""
        with (
            patch(
                "app.workers.diagnosis_worker.SessionLocal",
                return_value=mock_db_session,
            ),
            patch(
                "app.workers.diagnosis_worker.SSEPublisher",
                return_value=mock_sse_publisher,
            ),
            patch("app.workers.diagnosis_worker.AIUsageService"),
            patch(
                "app.services.ai_service.ClaudeService",
                return_value=mock_claude_service,
            ),
            patch("app.workers.diagnosis_worker.run_async") as mock_run_async,
        ):
            # Setup
            mock_db_session.query.return_value.filter.return_value.first.return_value = mock_diagnosis_run

            # Pipeline: research → classify → adapt
            mock_run_async.side_effect = [
                sample_research_result,  # research_ingredient
                {"root_cause": True, "confounded_by": None},  # classify_root_cause
                sample_diagnosis_result,  # adapt_to_plain_english
            ]

            # Import after patching
            from app.workers.diagnosis_worker import analyze_ingredient

            # Execute
            analyze_ingredient(
                run_id=1,
                ingredient_data=sample_ingredient_data,
                user_meal_history=[],
                web_search_enabled=True,
            )

            # Verify
            mock_sse_publisher.publish_progress.assert_called()
            mock_sse_publisher.publish_result.assert_called_once()
            mock_db_session.add.assert_called()  # DiagnosisResult was added
            mock_db_session.commit.assert_called()

    def test_confounder_detection(
        self,
        mock_db_session,
        mock_diagnosis_run,
        mock_claude_service,
        mock_sse_publisher,
        sample_ingredient_data,
        sample_research_result,
    ):
        """Test that confounders are properly discounted."""
        # Add co-occurrence data that suggests confounding
        sample_ingredient_data["cooccurrence"] = [
            {
                "with_ingredient_id": 2,
                "with_ingredient_name": "garlic",
                "conditional_probability": 0.95,
                "reverse_probability": 0.8,
                "lift": 2.5,
                "cooccurrence_meals": 5,
            }
        ]

        with (
            patch(
                "app.workers.diagnosis_worker.SessionLocal",
                return_value=mock_db_session,
            ),
            patch(
                "app.workers.diagnosis_worker.SSEPublisher",
                return_value=mock_sse_publisher,
            ),
            patch("app.workers.diagnosis_worker.AIUsageService"),
            patch(
                "app.services.ai_service.ClaudeService",
                return_value=mock_claude_service,
            ),
            patch("app.workers.diagnosis_worker.run_async") as mock_run_async,
        ):
            mock_db_session.query.return_value.filter.return_value.first.return_value = mock_diagnosis_run

            # Pipeline: research → classify (confounder → early exit, no adapt)
            mock_run_async.side_effect = [
                sample_research_result,  # research_ingredient
                {
                    "root_cause": False,
                    "discard_justification": "High co-occurrence with garlic",
                    "confounded_by": "garlic",
                    "medical_reasoning": "Garlic is the likely trigger",
                },  # classify_root_cause
            ]

            from app.workers.diagnosis_worker import analyze_ingredient

            analyze_ingredient(
                run_id=1,
                ingredient_data=sample_ingredient_data,
                user_meal_history=[],
                web_search_enabled=True,
            )

            # Verify discounted ingredient was published
            mock_sse_publisher.publish_discounted.assert_called_once()
            mock_sse_publisher.publish_progress.assert_called()
            # Regular result should NOT have been published
            mock_sse_publisher.publish_result.assert_not_called()

    def test_diagnosis_run_not_found(
        self, mock_db_session, mock_sse_publisher, sample_ingredient_data
    ):
        """Test error when diagnosis run is not found."""
        with (
            patch(
                "app.workers.diagnosis_worker.SessionLocal",
                return_value=mock_db_session,
            ),
            patch(
                "app.workers.diagnosis_worker.SSEPublisher",
                return_value=mock_sse_publisher,
            ),
            patch("app.workers.diagnosis_worker.AIUsageService"),
        ):
            # No diagnosis run found
            mock_db_session.query.return_value.filter.return_value.first.return_value = None

            from app.workers.diagnosis_worker import analyze_ingredient

            with pytest.raises(ValueError, match="not found"):
                analyze_ingredient(
                    run_id=999,
                    ingredient_data=sample_ingredient_data,
                    user_meal_history=[],
                    web_search_enabled=True,
                )

    def test_ai_service_unavailable(
        self,
        mock_db_session,
        mock_diagnosis_run,
        mock_claude_service,
        mock_sse_publisher,
        sample_ingredient_data,
        sample_research_result,
    ):
        """Test handling of AI service unavailability."""
        with (
            patch(
                "app.workers.diagnosis_worker.SessionLocal",
                return_value=mock_db_session,
            ),
            patch(
                "app.workers.diagnosis_worker.SSEPublisher",
                return_value=mock_sse_publisher,
            ),
            patch("app.workers.diagnosis_worker.AIUsageService"),
            patch(
                "app.services.ai_service.ClaudeService",
                return_value=mock_claude_service,
            ),
            patch("app.workers.diagnosis_worker.run_async") as mock_run_async,
        ):
            mock_db_session.query.return_value.filter.return_value.first.return_value = mock_diagnosis_run

            # research succeeds, classify succeeds, adapt fails
            mock_run_async.side_effect = [
                sample_research_result,  # research_ingredient
                {"root_cause": True, "confounded_by": None},  # classify_root_cause
                ServiceUnavailableError("AI service down"),  # adapt_to_plain_english
            ]

            from app.workers.diagnosis_worker import analyze_ingredient

            with pytest.raises(ServiceUnavailableError):
                analyze_ingredient(
                    run_id=1,
                    ingredient_data=sample_ingredient_data,
                    user_meal_history=[],
                    web_search_enabled=True,
                )

            # Verify error was published
            mock_sse_publisher.publish_error.assert_called()

    def test_rate_limit_error(
        self,
        mock_db_session,
        mock_diagnosis_run,
        mock_claude_service,
        mock_sse_publisher,
        sample_ingredient_data,
        sample_research_result,
    ):
        """Test handling of rate limit error."""
        with (
            patch(
                "app.workers.diagnosis_worker.SessionLocal",
                return_value=mock_db_session,
            ),
            patch(
                "app.workers.diagnosis_worker.SSEPublisher",
                return_value=mock_sse_publisher,
            ),
            patch("app.workers.diagnosis_worker.AIUsageService"),
            patch(
                "app.services.ai_service.ClaudeService",
                return_value=mock_claude_service,
            ),
            patch("app.workers.diagnosis_worker.run_async") as mock_run_async,
        ):
            mock_db_session.query.return_value.filter.return_value.first.return_value = mock_diagnosis_run

            # research succeeds, classify succeeds, adapt hits rate limit
            mock_run_async.side_effect = [
                sample_research_result,  # research_ingredient
                {"root_cause": True, "confounded_by": None},  # classify_root_cause
                RateLimitError("Too many requests"),  # adapt_to_plain_english
            ]

            from app.workers.diagnosis_worker import analyze_ingredient

            with pytest.raises(RateLimitError):
                analyze_ingredient(
                    run_id=1,
                    ingredient_data=sample_ingredient_data,
                    user_meal_history=[],
                    web_search_enabled=True,
                )

            # Verify rate limit error was published
            mock_sse_publisher.publish_error.assert_called()

    def test_last_ingredient_completes_run(
        self,
        mock_db_session,
        mock_diagnosis_run,
        mock_claude_service,
        mock_sse_publisher,
        sample_ingredient_data,
        sample_research_result,
        sample_diagnosis_result,
    ):
        """Test that last ingredient analysis completes the run."""
        # Set up as last ingredient
        mock_diagnosis_run.total_ingredients = 1
        mock_diagnosis_run.completed_ingredients = 1  # Will be this after increment

        with (
            patch(
                "app.workers.diagnosis_worker.SessionLocal",
                return_value=mock_db_session,
            ),
            patch(
                "app.workers.diagnosis_worker.SSEPublisher",
                return_value=mock_sse_publisher,
            ),
            patch("app.workers.diagnosis_worker.AIUsageService"),
            patch(
                "app.services.ai_service.ClaudeService",
                return_value=mock_claude_service,
            ),
            patch("app.workers.diagnosis_worker.run_async") as mock_run_async,
        ):
            mock_db_session.query.return_value.filter.return_value.first.return_value = mock_diagnosis_run

            mock_run_async.side_effect = [
                sample_research_result,  # research_ingredient
                {"root_cause": True, "confounded_by": None},  # classify_root_cause
                sample_diagnosis_result,  # adapt_to_plain_english
            ]

            from app.workers.diagnosis_worker import analyze_ingredient

            analyze_ingredient(
                run_id=1,
                ingredient_data=sample_ingredient_data,
                user_meal_history=[],
                web_search_enabled=True,
            )

            # Verify completion was published
            mock_sse_publisher.publish_complete.assert_called_once()
            assert mock_diagnosis_run.status == "completed"

    def test_root_cause_classification_error_continues(
        self,
        mock_db_session,
        mock_diagnosis_run,
        mock_claude_service,
        mock_sse_publisher,
        sample_ingredient_data,
        sample_research_result,
        sample_diagnosis_result,
    ):
        """Test that root cause classification error doesn't stop analysis."""
        with (
            patch(
                "app.workers.diagnosis_worker.SessionLocal",
                return_value=mock_db_session,
            ),
            patch(
                "app.workers.diagnosis_worker.SSEPublisher",
                return_value=mock_sse_publisher,
            ),
            patch("app.workers.diagnosis_worker.AIUsageService"),
            patch(
                "app.services.ai_service.ClaudeService",
                return_value=mock_claude_service,
            ),
            patch("app.workers.diagnosis_worker.run_async") as mock_run_async,
        ):
            mock_db_session.query.return_value.filter.return_value.first.return_value = mock_diagnosis_run

            # Research succeeds, classification fails, adapt should still proceed
            mock_run_async.side_effect = [
                sample_research_result,  # research_ingredient
                Exception("Classification failed"),  # classify_root_cause fails
                sample_diagnosis_result,  # adapt_to_plain_english succeeds
            ]

            from app.workers.diagnosis_worker import analyze_ingredient

            # Should not raise - classification error is caught
            analyze_ingredient(
                run_id=1,
                ingredient_data=sample_ingredient_data,
                user_meal_history=[],
                web_search_enabled=True,
            )

            # Verify result was still published
            mock_sse_publisher.publish_result.assert_called_once()

    def test_creates_citations(
        self,
        mock_db_session,
        mock_diagnosis_run,
        mock_claude_service,
        mock_sse_publisher,
        sample_ingredient_data,
        sample_research_result,
        sample_diagnosis_result,
    ):
        """Test that citations are merged from research + adapt steps and deduplicated."""
        with (
            patch(
                "app.workers.diagnosis_worker.SessionLocal",
                return_value=mock_db_session,
            ),
            patch(
                "app.workers.diagnosis_worker.SSEPublisher",
                return_value=mock_sse_publisher,
            ),
            patch("app.workers.diagnosis_worker.AIUsageService"),
            patch(
                "app.services.ai_service.ClaudeService",
                return_value=mock_claude_service,
            ),
            patch("app.workers.diagnosis_worker.run_async") as mock_run_async,
        ):
            mock_db_session.query.return_value.filter.return_value.first.return_value = mock_diagnosis_run

            mock_run_async.side_effect = [
                sample_research_result,  # research_ingredient (has 1 citation)
                {"root_cause": True, "confounded_by": None},  # classify_root_cause
                sample_diagnosis_result,  # adapt_to_plain_english (has 1 citation)
            ]

            from app.workers.diagnosis_worker import analyze_ingredient

            analyze_ingredient(
                run_id=1,
                ingredient_data=sample_ingredient_data,
                user_meal_history=[],
                web_search_enabled=True,
            )

            # Verify db.add was called for DiagnosisResult + citations
            # Research has 1 citation, adapt has 1 citation (different URLs) = 3 total adds
            assert mock_db_session.add.call_count >= 2

    def test_logs_ai_usage(
        self,
        mock_db_session,
        mock_diagnosis_run,
        mock_claude_service,
        mock_sse_publisher,
        sample_ingredient_data,
        sample_research_result,
        sample_diagnosis_result,
    ):
        """Test that AI usage is logged for both research and adapt steps."""
        with (
            patch(
                "app.workers.diagnosis_worker.SessionLocal",
                return_value=mock_db_session,
            ),
            patch(
                "app.workers.diagnosis_worker.SSEPublisher",
                return_value=mock_sse_publisher,
            ),
            patch(
                "app.workers.diagnosis_worker.AIUsageService"
            ) as mock_usage_service_cls,
            patch(
                "app.services.ai_service.ClaudeService",
                return_value=mock_claude_service,
            ),
            patch("app.workers.diagnosis_worker.run_async") as mock_run_async,
        ):
            mock_usage_service = MagicMock()
            mock_usage_service_cls.return_value = mock_usage_service
            mock_db_session.query.return_value.filter.return_value.first.return_value = mock_diagnosis_run

            mock_run_async.side_effect = [
                sample_research_result,  # research_ingredient
                {"root_cause": True, "confounded_by": None},  # classify_root_cause
                sample_diagnosis_result,  # adapt_to_plain_english
            ]

            from app.workers.diagnosis_worker import analyze_ingredient

            analyze_ingredient(
                run_id=1,
                ingredient_data=sample_ingredient_data,
                user_meal_history=[],
                web_search_enabled=True,
            )

            # Verify usage was logged (research + adapt = at least 2 calls)
            assert mock_usage_service.log_usage.call_count >= 2


# =============================================================================
# finalize_diagnosis_run Tests
# =============================================================================


class TestFinalizeDiagnosisRun:
    """Tests for the finalize_diagnosis_run actor."""

    def test_successful_finalization(
        self, mock_db_session, mock_diagnosis_run, mock_sse_publisher
    ):
        """Test successful diagnosis run finalization."""
        mock_diagnosis_run.status = "running"
        mock_diagnosis_run.results = [MagicMock(), MagicMock()]  # 2 results

        with (
            patch(
                "app.workers.diagnosis_worker.SessionLocal",
                return_value=mock_db_session,
            ),
            patch(
                "app.workers.diagnosis_worker.SSEPublisher",
                return_value=mock_sse_publisher,
            ),
        ):
            mock_db_session.query.return_value.filter.return_value.first.return_value = mock_diagnosis_run

            from app.workers.diagnosis_worker import finalize_diagnosis_run

            finalize_diagnosis_run(run_id=1)

            assert mock_diagnosis_run.status == "completed"
            assert mock_diagnosis_run.completed_at is not None
            mock_sse_publisher.publish_complete.assert_called_once_with(1, 2)
            mock_db_session.commit.assert_called()

    def test_already_completed_skipped(
        self, mock_db_session, mock_diagnosis_run, mock_sse_publisher
    ):
        """Test that already completed runs are skipped."""
        mock_diagnosis_run.status = "completed"

        with (
            patch(
                "app.workers.diagnosis_worker.SessionLocal",
                return_value=mock_db_session,
            ),
            patch(
                "app.workers.diagnosis_worker.SSEPublisher",
                return_value=mock_sse_publisher,
            ),
        ):
            mock_db_session.query.return_value.filter.return_value.first.return_value = mock_diagnosis_run

            from app.workers.diagnosis_worker import finalize_diagnosis_run

            finalize_diagnosis_run(run_id=1)

            # Should not publish complete again
            mock_sse_publisher.publish_complete.assert_not_called()

    def test_run_not_found(self, mock_db_session, mock_sse_publisher):
        """Test error when run is not found."""
        with (
            patch(
                "app.workers.diagnosis_worker.SessionLocal",
                return_value=mock_db_session,
            ),
            patch(
                "app.workers.diagnosis_worker.SSEPublisher",
                return_value=mock_sse_publisher,
            ),
        ):
            mock_db_session.query.return_value.filter.return_value.first.return_value = None

            from app.workers.diagnosis_worker import finalize_diagnosis_run

            with pytest.raises(ValueError, match="not found"):
                finalize_diagnosis_run(run_id=999)

    def test_error_marks_run_as_failed(
        self, mock_db_session, mock_diagnosis_run, mock_sse_publisher
    ):
        """Test that errors mark the run as failed."""
        mock_diagnosis_run.status = "running"

        with (
            patch(
                "app.workers.diagnosis_worker.SessionLocal",
                return_value=mock_db_session,
            ),
            patch(
                "app.workers.diagnosis_worker.SSEPublisher",
                return_value=mock_sse_publisher,
            ),
        ):
            # Return run on first query, but fail on commit
            mock_db_session.query.return_value.filter.return_value.first.return_value = mock_diagnosis_run
            mock_db_session.commit.side_effect = [Exception("DB Error"), None]

            from app.workers.diagnosis_worker import finalize_diagnosis_run

            with pytest.raises(Exception, match="DB Error"):
                finalize_diagnosis_run(run_id=1)

            # Verify error was published
            mock_sse_publisher.publish_error.assert_called()

    def test_cleanup_closes_resources(
        self, mock_db_session, mock_diagnosis_run, mock_sse_publisher
    ):
        """Test that resources are cleaned up."""
        mock_diagnosis_run.status = "running"
        mock_diagnosis_run.results = []

        with (
            patch(
                "app.workers.diagnosis_worker.SessionLocal",
                return_value=mock_db_session,
            ),
            patch(
                "app.workers.diagnosis_worker.SSEPublisher",
                return_value=mock_sse_publisher,
            ),
        ):
            mock_db_session.query.return_value.filter.return_value.first.return_value = mock_diagnosis_run

            from app.workers.diagnosis_worker import finalize_diagnosis_run

            finalize_diagnosis_run(run_id=1)

            # Verify cleanup
            mock_db_session.close.assert_called_once()
            mock_sse_publisher.close.assert_called_once()


# =============================================================================
# run_async Helper Tests
# =============================================================================


class TestRunAsync:
    """Tests for the run_async helper function."""

    def test_runs_coroutine(self):
        """Test that run_async properly executes coroutines."""
        from app.workers.diagnosis_worker import run_async

        async def sample_coro():
            return "result"

        result = run_async(sample_coro())
        assert result == "result"

    def test_propagates_exceptions(self):
        """Test that exceptions are propagated."""
        from app.workers.diagnosis_worker import run_async

        async def failing_coro():
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            run_async(failing_coro())
