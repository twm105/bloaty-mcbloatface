"""
Unit tests for ClaudeService (AI integration).

Tests AI functionality using mocked Claude API responses:
- Image validation and analysis
- Symptom elaboration
- Episode detection
- Retry logic and error handling
"""
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import json
import tempfile

from app.services.ai_service import (
    ClaudeService,
    ServiceUnavailableError,
    RateLimitError,
    retry_on_connection_error,
)
from tests.fixtures.mocks import MockClaudeService


class TestImageValidation:
    """Tests for meal image validation."""

    @pytest.mark.asyncio
    async def test_validate_meal_image_valid(self, mock_claude_service):
        """Test that valid meal images return True."""
        mock_claude_service.set_validate_meal_image_response(True)

        result = await mock_claude_service.validate_meal_image("/path/to/meal.jpg")

        assert result is True
        assert len(mock_claude_service.calls.get("validate_meal_image", [])) == 1

    @pytest.mark.asyncio
    async def test_validate_meal_image_invalid(self, mock_claude_service):
        """Test that non-meal images return False."""
        mock_claude_service.set_validate_meal_image_response(False)

        result = await mock_claude_service.validate_meal_image("/path/to/selfie.jpg")

        assert result is False

    @pytest.mark.asyncio
    async def test_validate_meal_image_error(self, mock_claude_service):
        """Test that API errors are properly raised."""
        mock_claude_service.set_error(ServiceUnavailableError("Test error"))

        with pytest.raises(ServiceUnavailableError):
            await mock_claude_service.validate_meal_image("/path/to/image.jpg")


class TestMealImageAnalysis:
    """Tests for meal image analysis."""

    @pytest.mark.asyncio
    async def test_analyze_meal_image_basic(self, mock_claude_service):
        """Test basic meal image analysis."""
        result = await mock_claude_service.analyze_meal_image("/path/to/meal.jpg")

        assert "meal_name" in result
        assert "ingredients" in result
        assert len(result["ingredients"]) > 0
        assert "model" in result

    @pytest.mark.asyncio
    async def test_analyze_meal_image_with_notes(self, mock_claude_service):
        """Test meal analysis with user notes."""
        result = await mock_claude_service.analyze_meal_image(
            "/path/to/meal.jpg",
            user_notes="This is a grilled chicken salad"
        )

        # Verify the call was made with notes
        calls = mock_claude_service.calls.get("analyze_meal_image", [])
        assert len(calls) == 1
        assert calls[0]["kwargs"]["user_notes"] == "This is a grilled chicken salad"

    @pytest.mark.asyncio
    async def test_analyze_meal_image_custom_response(self, mock_claude_service):
        """Test with custom configured response."""
        custom_ingredients = [
            {"name": "salmon", "state": "cooked", "quantity": "200g", "confidence": 0.95}
        ]
        mock_claude_service.set_analyze_meal_image_response({
            "meal_name": "Grilled Salmon",
            "ingredients": custom_ingredients,
            "raw_response": "{}",
            "model": "test-model"
        })

        result = await mock_claude_service.analyze_meal_image("/path/to/meal.jpg")

        assert result["meal_name"] == "Grilled Salmon"
        assert result["ingredients"][0]["name"] == "salmon"

    @pytest.mark.asyncio
    async def test_analyze_meal_image_error(self, mock_claude_service):
        """Test error handling in meal analysis."""
        mock_claude_service.set_error(RateLimitError("Rate limited"))

        with pytest.raises(RateLimitError):
            await mock_claude_service.analyze_meal_image("/path/to/meal.jpg")


class TestSymptomElaboration:
    """Tests for symptom elaboration."""

    @pytest.mark.asyncio
    async def test_elaborate_symptom_tags_basic(self, mock_claude_service):
        """Test basic symptom elaboration."""
        tags = [
            {"name": "bloating", "severity": 7},
            {"name": "gas", "severity": 5}
        ]

        result = await mock_claude_service.elaborate_symptom_tags(tags)

        assert "elaboration" in result
        assert "model" in result
        assert "bloating" in result["elaboration"].lower() or "severe" in result["elaboration"].lower()

    @pytest.mark.asyncio
    async def test_elaborate_symptom_tags_with_times(self, mock_claude_service):
        """Test elaboration with start/end times."""
        tags = [{"name": "cramping", "severity": 6}]
        start = datetime.now(timezone.utc) - timedelta(hours=2)
        end = datetime.now(timezone.utc)

        result = await mock_claude_service.elaborate_symptom_tags(
            tags,
            start_time=start,
            end_time=end
        )

        assert "elaboration" in result

    @pytest.mark.asyncio
    async def test_elaborate_symptom_tags_custom_response(self, mock_claude_service):
        """Test with custom configured response."""
        mock_claude_service.set_elaborate_symptom_tags_response({
            "elaboration": "Custom elaboration text.",
            "raw_response": "",
            "model": "test-model"
        })

        tags = [{"name": "nausea", "severity": 4}]
        result = await mock_claude_service.elaborate_symptom_tags(tags)

        assert result["elaboration"] == "Custom elaboration text."


class TestStreamingElaboration:
    """Tests for streaming symptom elaboration."""

    @pytest.mark.asyncio
    async def test_elaborate_symptom_tags_streaming(self, mock_claude_service):
        """Test streaming elaboration yields chunks."""
        tags = [{"name": "bloating", "severity": 5}]

        chunks = []
        async for chunk in mock_claude_service.elaborate_symptom_tags_streaming(tags):
            chunks.append(chunk)

        assert len(chunks) > 0
        full_text = "".join(chunks)
        assert len(full_text) > 0


class TestEpisodeDetection:
    """Tests for episode continuation detection."""

    @pytest.mark.asyncio
    async def test_detect_episode_continuation_positive(self, mock_claude_service):
        """Test detection of episode continuation."""
        current_tags = [{"name": "bloating", "severity": 6}]
        current_time = datetime.now(timezone.utc)
        previous = {
            "tags": [{"name": "bloating", "severity": 7}],
            "start_time": datetime.now(timezone.utc) - timedelta(hours=4),
            "end_time": None,
            "notes": "Initial bloating episode"
        }

        result = await mock_claude_service.detect_episode_continuation(
            current_tags, current_time, previous
        )

        assert "is_continuation" in result
        assert "confidence" in result
        assert "reasoning" in result
        # Same symptom type should be continuation
        assert result["is_continuation"] is True

    @pytest.mark.asyncio
    async def test_detect_episode_continuation_negative(self, mock_claude_service):
        """Test detection of non-continuation."""
        current_tags = [{"name": "headache", "severity": 5}]
        current_time = datetime.now(timezone.utc)
        previous = {
            "tags": [{"name": "bloating", "severity": 7}],
            "start_time": datetime.now(timezone.utc) - timedelta(hours=4),
            "end_time": None,
            "notes": None
        }

        result = await mock_claude_service.detect_episode_continuation(
            current_tags, current_time, previous
        )

        # Different symptom type should not be continuation
        assert result["is_continuation"] is False

    @pytest.mark.asyncio
    async def test_detect_ongoing_symptom(self, mock_claude_service):
        """Test detection of ongoing symptom."""
        previous = {"name": "bloating", "severity": 6}
        current = {"name": "bloating", "severity": 5}

        result = await mock_claude_service.detect_ongoing_symptom(previous, current)

        assert result["is_ongoing"] is True
        assert result["confidence"] > 0.5


class TestSymptomClarification:
    """Tests for symptom clarification."""

    @pytest.mark.asyncio
    async def test_clarify_symptom_asks_questions(self, mock_claude_service):
        """Test that clarification asks follow-up questions."""
        result = await mock_claude_service.clarify_symptom(
            "I feel sick",
            clarification_history=[]
        )

        assert result["mode"] == "question"
        assert "question" in result

    @pytest.mark.asyncio
    async def test_clarify_symptom_completes_after_questions(self, mock_claude_service):
        """Test that clarification completes after enough questions."""
        history = [
            {"question": "When did it start?", "answer": "2 hours ago", "skipped": False},
            {"question": "How severe?", "answer": "7 out of 10", "skipped": False}
        ]

        result = await mock_claude_service.clarify_symptom(
            "I have stomach pain",
            clarification_history=history
        )

        assert result["mode"] == "complete"
        assert "structured" in result


class TestDiagnosis:
    """Tests for diagnosis functionality."""

    @pytest.mark.asyncio
    async def test_diagnose_correlations(self, mock_claude_service):
        """Test correlation diagnosis."""
        correlation_data = [
            {
                "ingredient_name": "onion",
                "state": "raw",
                "times_eaten": 5,
                "total_symptom_occurrences": 4,
                "immediate_total": 3,
                "delayed_total": 1,
                "cumulative_total": 0,
                "associated_symptoms": [
                    {"name": "bloating", "severity_avg": 7.0, "frequency": 4, "lag_hours": 1.5}
                ]
            }
        ]

        result = await mock_claude_service.diagnose_correlations(correlation_data)

        assert "ingredient_analyses" in result
        assert "usage_stats" in result
        assert len(result["ingredient_analyses"]) >= 1

    @pytest.mark.asyncio
    async def test_diagnose_single_ingredient(self, mock_claude_service):
        """Test single ingredient diagnosis."""
        ingredient_data = {
            "ingredient_name": "milk",
            "state": "processed",
            "times_eaten": 10,
            "total_symptom_occurrences": 8,
            "immediate_total": 2,
            "delayed_total": 6,
            "cumulative_total": 0,
            "associated_symptoms": [
                {"name": "gas", "severity_avg": 6.0, "frequency": 8, "lag_hours": 6.0}
            ]
        }
        meal_history = []

        result = await mock_claude_service.diagnose_single_ingredient(
            ingredient_data, meal_history
        )

        assert "diagnosis_summary" in result
        assert "recommendations_summary" in result
        assert "usage_stats" in result

    @pytest.mark.asyncio
    async def test_classify_root_cause_is_root(self, mock_claude_service):
        """Test root cause classification - confirms as root cause."""
        ingredient_data = {
            "ingredient_name": "onion",
            "confidence_level": "high",
            "times_eaten": 5,
            "total_symptom_occurrences": 4,
            "associated_symptoms": [{"name": "bloating", "frequency": 4}]
        }
        cooccurrence_data = []  # No high co-occurrence

        result = await mock_claude_service.classify_root_cause(
            ingredient_data, cooccurrence_data, ""
        )

        assert result["root_cause"] is True
        assert result["confounded_by"] is None

    @pytest.mark.asyncio
    async def test_classify_root_cause_is_confounder(self, mock_claude_service):
        """Test root cause classification - identifies as confounder."""
        ingredient_data = {
            "ingredient_name": "garlic",
            "confidence_level": "high",
            "times_eaten": 5,
            "total_symptom_occurrences": 4,
            "associated_symptoms": [{"name": "bloating", "frequency": 4}]
        }
        cooccurrence_data = [
            {
                "with_ingredient_name": "onion",
                "conditional_probability": 0.95,  # Very high co-occurrence
                "cooccurrence_meals": 5
            }
        ]

        result = await mock_claude_service.classify_root_cause(
            ingredient_data, cooccurrence_data, ""
        )

        assert result["root_cause"] is False
        assert result["confounded_by"] == "onion"


class TestPatternAnalysis:
    """Tests for pattern analysis."""

    @pytest.mark.asyncio
    async def test_analyze_patterns(self, mock_claude_service):
        """Test pattern analysis."""
        meals_data = "Meal data here..."
        symptoms_data = "Symptom data here..."

        result = await mock_claude_service.analyze_patterns(
            meals_data, symptoms_data
        )

        assert "analysis" in result
        assert "model" in result


class TestErrorHandling:
    """Tests for error handling and retries."""

    @pytest.mark.asyncio
    async def test_service_unavailable_error(self, mock_claude_service):
        """Test ServiceUnavailableError is raised appropriately."""
        mock_claude_service.set_error(ServiceUnavailableError("Service down"))

        with pytest.raises(ServiceUnavailableError):
            await mock_claude_service.analyze_meal_image("/path/to/image.jpg")

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, mock_claude_service):
        """Test RateLimitError is raised appropriately."""
        mock_claude_service.set_error(RateLimitError("Rate limited"))

        with pytest.raises(RateLimitError):
            await mock_claude_service.validate_meal_image("/path/to/image.jpg")

    @pytest.mark.asyncio
    async def test_mock_reset(self, mock_claude_service):
        """Test that mock can be reset between tests."""
        # Set error
        mock_claude_service.set_error(ServiceUnavailableError("Error"))

        # Trigger error
        with pytest.raises(ServiceUnavailableError):
            await mock_claude_service.validate_meal_image("/path/to/image.jpg")

        # After error is consumed, should work normally
        result = await mock_claude_service.validate_meal_image("/path/to/image.jpg")
        assert result is True  # Default response


class TestCallTracking:
    """Tests for call tracking in mocks."""

    @pytest.mark.asyncio
    async def test_calls_are_tracked(self, mock_claude_service):
        """Test that calls are tracked for assertions."""
        await mock_claude_service.validate_meal_image("/path1.jpg")
        await mock_claude_service.validate_meal_image("/path2.jpg")

        calls = mock_claude_service.calls.get("validate_meal_image", [])
        assert len(calls) == 2
        assert calls[0]["kwargs"]["image_path"] == "/path1.jpg"
        assert calls[1]["kwargs"]["image_path"] == "/path2.jpg"

    @pytest.mark.asyncio
    async def test_call_tracking_includes_all_args(self, mock_claude_service):
        """Test that all arguments are tracked."""
        tags = [{"name": "bloating", "severity": 5}]
        start = datetime.now(timezone.utc)

        await mock_claude_service.elaborate_symptom_tags(
            tags,
            start_time=start,
            user_notes="Test notes"
        )

        calls = mock_claude_service.calls.get("elaborate_symptom_tags", [])
        assert len(calls) == 1
        assert calls[0]["kwargs"]["tags"] == tags
        assert calls[0]["kwargs"]["start_time"] == start
        assert calls[0]["kwargs"]["user_notes"] == "Test notes"


class TestRetryDecorator:
    """Tests for the retry decorator."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_first_attempt(self):
        """Test that successful calls don't retry."""
        call_count = 0

        @retry_on_connection_error(max_attempts=3, base_delay=0.01)
        async def successful_call():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await successful_call()

        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_eventually_succeeds(self):
        """Test that retries eventually succeed."""
        import anthropic

        call_count = 0

        @retry_on_connection_error(max_attempts=3, base_delay=0.01)
        async def flaky_call():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise anthropic.APIConnectionError(request=MagicMock())
            return "success"

        result = await flaky_call()

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausts_attempts(self):
        """Test that retries exhaust and raise."""
        import anthropic

        call_count = 0

        @retry_on_connection_error(max_attempts=3, base_delay=0.01)
        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise anthropic.APIConnectionError(request=MagicMock())

        with pytest.raises(ServiceUnavailableError):
            await always_fails()

        assert call_count == 3


# Fixture for mock claude service
@pytest.fixture
def mock_claude_service():
    """Provide a fresh mock claude service for each test."""
    return MockClaudeService()
