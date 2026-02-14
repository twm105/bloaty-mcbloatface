"""
Unit tests for ClaudeService - testing REAL code paths with mocked Anthropic client.

These tests exercise the actual ClaudeService implementation, not MockClaudeService.
The Anthropic client is mocked at a low level to avoid real API calls while
testing all code branches, error handling, and response parsing.
"""

import pytest
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
import anthropic

from app.services.ai_service import (
    ClaudeService,
    ServiceUnavailableError,
    RateLimitError,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_anthropic_client():
    """Create a mock Anthropic client."""
    with patch("app.services.ai_service.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        yield mock_client


@pytest.fixture
def claude_service(mock_anthropic_client):
    """Create a ClaudeService instance with mocked Anthropic client."""
    service = ClaudeService()
    service.client = mock_anthropic_client
    return service


@pytest.fixture
def sample_image_file():
    """Create a temporary image file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        # Write minimal JPEG header
        f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00")
        f.flush()
        yield f.name
    Path(f.name).unlink(missing_ok=True)


def create_mock_response(text: str, usage: dict = None):
    """Helper to create mock API response."""
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = text
    mock_response.content = [mock_content]
    mock_response.usage = MagicMock()
    mock_response.usage.input_tokens = usage.get("input_tokens", 100) if usage else 100
    mock_response.usage.output_tokens = usage.get("output_tokens", 50) if usage else 50
    mock_response.usage.cache_read_input_tokens = (
        usage.get("cache_read_input_tokens", 0) if usage else 0
    )
    return mock_response


# =============================================================================
# Image Validation Tests
# =============================================================================


class TestValidateMealImage:
    """Tests for validate_meal_image method."""

    @pytest.mark.asyncio
    async def test_valid_meal_image(self, claude_service, sample_image_file):
        """Test that valid meal images return True."""
        claude_service.client.messages.create.return_value = create_mock_response("YES")

        result = await claude_service.validate_meal_image(sample_image_file)

        assert result is True
        claude_service.client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_meal_image(self, claude_service, sample_image_file):
        """Test that non-meal images return False."""
        claude_service.client.messages.create.return_value = create_mock_response("NO")

        result = await claude_service.validate_meal_image(sample_image_file)

        assert result is False

    @pytest.mark.asyncio
    async def test_case_insensitive_response(self, claude_service, sample_image_file):
        """Test that response parsing is case-insensitive."""
        claude_service.client.messages.create.return_value = create_mock_response("yes")

        result = await claude_service.validate_meal_image(sample_image_file)

        assert result is True

    @pytest.mark.asyncio
    async def test_whitespace_trimmed(self, claude_service, sample_image_file):
        """Test that whitespace in response is trimmed."""
        claude_service.client.messages.create.return_value = create_mock_response(
            "  YES  \n"
        )

        result = await claude_service.validate_meal_image(sample_image_file)

        assert result is True

    @pytest.mark.asyncio
    async def test_api_connection_error(self, claude_service, sample_image_file):
        """Test that APIConnectionError raises ServiceUnavailableError."""
        claude_service.client.messages.create.side_effect = (
            anthropic.APIConnectionError(request=MagicMock())
        )

        with pytest.raises(ServiceUnavailableError):
            await claude_service.validate_meal_image(sample_image_file)

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, claude_service, sample_image_file):
        """Test that RateLimitError is raised on rate limiting."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        claude_service.client.messages.create.side_effect = anthropic.RateLimitError(
            message="Rate limited", response=mock_response, body={}
        )

        with pytest.raises(RateLimitError):
            await claude_service.validate_meal_image(sample_image_file)

    @pytest.mark.asyncio
    async def test_server_error(self, claude_service, sample_image_file):
        """Test that 5xx errors raise ServiceUnavailableError."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        claude_service.client.messages.create.side_effect = anthropic.APIStatusError(
            message="Server error", response=mock_response, body={}
        )

        with pytest.raises(ServiceUnavailableError):
            await claude_service.validate_meal_image(sample_image_file)

    @pytest.mark.asyncio
    async def test_client_error(self, claude_service, sample_image_file):
        """Test that 4xx errors (non-rate limit) raise ValueError."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        claude_service.client.messages.create.side_effect = anthropic.APIStatusError(
            message="Bad request", response=mock_response, body={}
        )

        with pytest.raises(ValueError, match="Request error"):
            await claude_service.validate_meal_image(sample_image_file)


# =============================================================================
# Meal Image Analysis Tests
# =============================================================================


class TestAnalyzeMealImage:
    """Tests for analyze_meal_image method."""

    @pytest.mark.asyncio
    async def test_basic_analysis(self, claude_service, sample_image_file):
        """Test basic meal image analysis."""
        response_json = json.dumps(
            {
                "meal_name": "Grilled Chicken Salad",
                "ingredients": [
                    {
                        "name": "chicken",
                        "state": "cooked",
                        "quantity": "150g",
                        "confidence": 0.9,
                    }
                ],
            }
        )
        claude_service.client.messages.create.return_value = create_mock_response(
            response_json
        )

        result = await claude_service.analyze_meal_image(sample_image_file)

        assert result["meal_name"] == "Grilled Chicken Salad"
        assert len(result["ingredients"]) == 1
        assert result["ingredients"][0]["name"] == "chicken"
        assert "model" in result

    @pytest.mark.asyncio
    async def test_analysis_with_user_notes(self, claude_service, sample_image_file):
        """Test analysis with user-provided notes."""
        response_json = json.dumps(
            {
                "meal_name": "Pasta",
                "ingredients": [
                    {
                        "name": "pasta",
                        "state": "cooked",
                        "quantity": "200g",
                        "confidence": 0.95,
                    }
                ],
            }
        )
        claude_service.client.messages.create.return_value = create_mock_response(
            response_json
        )

        result = await claude_service.analyze_meal_image(
            sample_image_file, user_notes="This is pasta"
        )

        assert result["meal_name"] == "Pasta"
        # Verify notes were included in the call
        call_args = claude_service.client.messages.create.call_args
        messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))
        user_message_content = messages[0]["content"]
        # Notes should be in the message content
        assert any("This is pasta" in str(item) for item in user_message_content)

    @pytest.mark.asyncio
    async def test_json_in_markdown_block(self, claude_service, sample_image_file):
        """Test parsing JSON wrapped in markdown code block."""
        response = """```json
{
    "meal_name": "Salad",
    "ingredients": [{"name": "lettuce", "state": "raw", "quantity": "100g", "confidence": 0.85}]
}
```"""
        claude_service.client.messages.create.return_value = create_mock_response(
            response
        )

        result = await claude_service.analyze_meal_image(sample_image_file)

        assert result["meal_name"] == "Salad"
        assert result["ingredients"][0]["name"] == "lettuce"

    @pytest.mark.asyncio
    async def test_json_in_plain_code_block(self, claude_service, sample_image_file):
        """Test parsing JSON wrapped in plain code block."""
        response = """```
{
    "meal_name": "Soup",
    "ingredients": [{"name": "broth", "state": "cooked", "quantity": "300ml", "confidence": 0.8}]
}
```"""
        claude_service.client.messages.create.return_value = create_mock_response(
            response
        )

        result = await claude_service.analyze_meal_image(sample_image_file)

        assert result["meal_name"] == "Soup"

    @pytest.mark.asyncio
    async def test_missing_meal_name_uses_default(
        self, claude_service, sample_image_file
    ):
        """Test that missing meal_name uses default."""
        response_json = json.dumps(
            {
                "ingredients": [
                    {
                        "name": "rice",
                        "state": "cooked",
                        "quantity": "1 cup",
                        "confidence": 0.9,
                    }
                ]
            }
        )
        claude_service.client.messages.create.return_value = create_mock_response(
            response_json
        )

        result = await claude_service.analyze_meal_image(sample_image_file)

        assert result["meal_name"] == "Untitled Meal"

    @pytest.mark.asyncio
    async def test_invalid_json_raises_error(self, claude_service, sample_image_file):
        """Test that invalid JSON response raises ValueError."""
        claude_service.client.messages.create.return_value = create_mock_response(
            "Not valid JSON {"
        )

        with pytest.raises(ValueError, match="parse"):
            await claude_service.analyze_meal_image(sample_image_file)

    @pytest.mark.asyncio
    async def test_api_errors_propagate(self, claude_service, sample_image_file):
        """Test that API errors are properly converted."""
        claude_service.client.messages.create.side_effect = (
            anthropic.APIConnectionError(request=MagicMock())
        )

        with pytest.raises(ServiceUnavailableError):
            await claude_service.analyze_meal_image(sample_image_file)


# =============================================================================
# Symptom Elaboration Tests
# =============================================================================


class TestElaborateSymptomTags:
    """Tests for elaborate_symptom_tags method."""

    @pytest.mark.asyncio
    async def test_basic_elaboration(self, claude_service):
        """Test basic symptom elaboration."""
        claude_service.client.messages.create.return_value = create_mock_response(
            "Patient experienced moderate bloating and gas."
        )

        tags = [{"name": "bloating", "severity": 5}, {"name": "gas", "severity": 4}]
        result = await claude_service.elaborate_symptom_tags(tags)

        assert "elaboration" in result
        assert "bloating" in result["elaboration"].lower()
        assert "model" in result

    @pytest.mark.asyncio
    async def test_elaboration_with_times(self, claude_service):
        """Test elaboration with start and end times."""
        claude_service.client.messages.create.return_value = create_mock_response(
            "Patient experienced symptoms for 2 hours."
        )

        tags = [{"name": "cramping", "severity": 6}]
        start = datetime.now(timezone.utc)
        end = datetime.now(timezone.utc)

        result = await claude_service.elaborate_symptom_tags(
            tags, start_time=start, end_time=end
        )

        assert "elaboration" in result
        # Verify times were included in request
        call_args = claude_service.client.messages.create.call_args
        messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))
        assert "Start time" in str(messages)

    @pytest.mark.asyncio
    async def test_elaboration_with_notes(self, claude_service):
        """Test elaboration with user notes."""
        claude_service.client.messages.create.return_value = create_mock_response(
            "Symptoms noted after eating dairy."
        )

        tags = [{"name": "nausea", "severity": 4}]
        result = await claude_service.elaborate_symptom_tags(
            tags, user_notes="Happened after drinking milk"
        )

        assert "elaboration" in result
        call_args = claude_service.client.messages.create.call_args
        messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))
        assert "drinking milk" in str(messages)


# =============================================================================
# Episode Continuation Detection Tests
# =============================================================================


class TestDetectEpisodeContinuation:
    """Tests for detect_episode_continuation method."""

    @pytest.mark.asyncio
    async def test_continuation_detected(self, claude_service):
        """Test that continuation is detected."""
        response_json = json.dumps(
            {
                "is_continuation": True,
                "confidence": 0.9,
                "reasoning": "Same symptom type within episode window",
            }
        )
        claude_service.client.messages.create.return_value = create_mock_response(
            response_json
        )

        current_tags = [{"name": "bloating", "severity": 6}]
        current_time = datetime.now(timezone.utc)
        previous = {
            "tags": [{"name": "bloating", "severity": 7}],
            "start_time": datetime.now(timezone.utc),
            "end_time": None,
            "notes": "Initial episode",
        }

        result = await claude_service.detect_episode_continuation(
            current_tags, current_time, previous
        )

        assert result["is_continuation"] is True
        assert result["confidence"] == 0.9
        assert "reasoning" in result

    @pytest.mark.asyncio
    async def test_continuation_not_detected(self, claude_service):
        """Test that non-continuation is detected."""
        response_json = json.dumps(
            {
                "is_continuation": False,
                "confidence": 0.2,
                "reasoning": "Different symptom pattern",
            }
        )
        claude_service.client.messages.create.return_value = create_mock_response(
            response_json
        )

        current_tags = [{"name": "headache", "severity": 5}]
        current_time = datetime.now(timezone.utc)
        previous = {
            "tags": [{"name": "bloating", "severity": 7}],
            "start_time": datetime.now(timezone.utc),
            "end_time": None,
            "notes": None,
        }

        result = await claude_service.detect_episode_continuation(
            current_tags, current_time, previous
        )

        assert result["is_continuation"] is False

    @pytest.mark.asyncio
    async def test_json_in_code_block(self, claude_service):
        """Test parsing JSON wrapped in code block."""
        response = """```json
{"is_continuation": true, "confidence": 0.85, "reasoning": "Similar symptoms"}
```"""
        claude_service.client.messages.create.return_value = create_mock_response(
            response
        )

        result = await claude_service.detect_episode_continuation(
            [{"name": "bloating", "severity": 5}],
            datetime.now(timezone.utc),
            {
                "tags": [],
                "start_time": datetime.now(timezone.utc),
                "end_time": None,
                "notes": None,
            },
        )

        assert result["is_continuation"] is True

    @pytest.mark.asyncio
    async def test_invalid_json_raises_error(self, claude_service):
        """Test that invalid JSON raises ValueError."""
        claude_service.client.messages.create.return_value = create_mock_response(
            "Not JSON"
        )

        with pytest.raises(ValueError, match="parse"):
            await claude_service.detect_episode_continuation(
                [{"name": "test", "severity": 5}],
                datetime.now(timezone.utc),
                {
                    "tags": [],
                    "start_time": datetime.now(timezone.utc),
                    "end_time": None,
                    "notes": None,
                },
            )


# =============================================================================
# Symptom Clarification Tests
# =============================================================================


class TestClarifySymptom:
    """Tests for clarify_symptom method."""

    @pytest.mark.asyncio
    async def test_asks_question(self, claude_service):
        """Test that clarification asks a follow-up question."""
        response_json = json.dumps(
            {"mode": "question", "question": "When did the symptoms start?"}
        )
        claude_service.client.messages.create.return_value = create_mock_response(
            response_json
        )

        result = await claude_service.clarify_symptom("I feel sick")

        assert result["mode"] == "question"
        assert "question" in result

    @pytest.mark.asyncio
    async def test_completes_with_structured_data(self, claude_service):
        """Test that clarification completes with structured data."""
        response_json = json.dumps(
            {
                "mode": "complete",
                "structured": {
                    "type": "bloating",
                    "severity": 6,
                    "notes": "After eating dairy",
                },
            }
        )
        claude_service.client.messages.create.return_value = create_mock_response(
            response_json
        )

        history = [
            {
                "question": "When did it start?",
                "answer": "2 hours ago",
                "skipped": False,
            }
        ]
        result = await claude_service.clarify_symptom("stomach pain", history)

        assert result["mode"] == "complete"
        assert "structured" in result

    @pytest.mark.asyncio
    async def test_handles_skipped_questions(self, claude_service):
        """Test that skipped questions are handled."""
        response_json = json.dumps(
            {
                "mode": "complete",
                "structured": {"type": "nausea", "severity": 5, "notes": ""},
            }
        )
        claude_service.client.messages.create.return_value = create_mock_response(
            response_json
        )

        history = [{"question": "How severe?", "answer": "", "skipped": True}]
        result = await claude_service.clarify_symptom("feeling nauseous", history)

        assert result["mode"] == "complete"

    @pytest.mark.asyncio
    async def test_json_in_markdown_block(self, claude_service):
        """Test parsing JSON wrapped in markdown."""
        response = """```json
{"mode": "question", "question": "How severe is the pain?"}
```"""
        claude_service.client.messages.create.return_value = create_mock_response(
            response
        )

        result = await claude_service.clarify_symptom("stomach pain")

        assert result["mode"] == "question"


# =============================================================================
# Diagnosis Tests
# =============================================================================


class TestDiagnoseCorrelations:
    """Tests for diagnose_correlations method."""

    @pytest.mark.asyncio
    async def test_basic_diagnosis(self, claude_service):
        """Test basic correlation diagnosis."""
        response_json = json.dumps(
            {
                "ingredient_analyses": [
                    {
                        "ingredient_name": "onion",
                        "medical_context": "FODMAPs content may cause symptoms",
                        "interpretation": "Strong correlation observed",
                        "recommendations": "Try elimination diet",
                    }
                ],
                "overall_summary": "Analysis complete",
                "caveats": ["Correlation is not causation"],
            }
        )
        # Prepend opening brace since we use prefill
        mock_response = create_mock_response(response_json[1:])  # Remove leading '{'
        claude_service.client.messages.create.return_value = mock_response

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
                    {
                        "name": "bloating",
                        "severity_avg": 7.0,
                        "frequency": 4,
                        "lag_hours": 1.5,
                    }
                ],
            }
        ]

        result = await claude_service.diagnose_correlations(correlation_data)

        assert "ingredient_analyses" in result
        assert "usage_stats" in result

    @pytest.mark.asyncio
    async def test_diagnosis_without_web_search(self, claude_service):
        """Test diagnosis with web search disabled."""
        response_json = json.dumps(
            {
                "ingredient_analyses": [],
                "overall_summary": "No significant correlations",
                "caveats": [],
            }
        )
        mock_response = create_mock_response(response_json[1:])
        claude_service.client.messages.create.return_value = mock_response

        await claude_service.diagnose_correlations([], web_search_enabled=False)

        # Verify web_search tool was not included
        call_args = claude_service.client.messages.create.call_args
        tools = call_args.kwargs.get("tools", [])
        assert len(tools) == 0


class TestDiagnoseSingleIngredient:
    """Tests for diagnose_single_ingredient method."""

    @pytest.mark.asyncio
    async def test_single_ingredient_diagnosis(self, claude_service):
        """Test single ingredient diagnosis."""
        response_json = json.dumps(
            {
                "diagnosis_summary": "Milk shows correlation with digestive symptoms.",
                "recommendations_summary": "Consider lactose-free alternatives.",
                "processing_suggestions": {
                    "cooked_vs_raw": "Processing may help",
                    "alternatives": ["oat milk", "almond milk"],
                },
                "alternative_meals": [],
                "citations": [
                    {
                        "url": "https://www.nih.gov/example",
                        "title": "Lactose Intolerance",
                        "source_type": "nih",
                        "snippet": "Information about lactose intolerance",
                    }
                ],
            }
        )
        mock_response = create_mock_response(response_json[1:])
        claude_service.client.messages.create.return_value = mock_response

        ingredient_data = {
            "ingredient_id": 1,
            "ingredient_name": "milk",
            "state": "processed",
            "times_eaten": 10,
            "total_symptom_occurrences": 8,
            "immediate_total": 2,
            "delayed_total": 6,
            "cumulative_total": 0,
            "confidence_score": 0.8,
            "confidence_level": "high",
            "associated_symptoms": [
                {"name": "gas", "severity_avg": 6.0, "frequency": 8, "lag_hours": 6.0}
            ],
        }

        result = await claude_service.diagnose_single_ingredient(ingredient_data, [])

        assert "diagnosis_summary" in result
        assert "recommendations_summary" in result
        assert "usage_stats" in result


class TestClassifyRootCause:
    """Tests for classify_root_cause method."""

    @pytest.mark.asyncio
    async def test_identifies_root_cause(self, claude_service):
        """Test that root cause is correctly identified."""
        response_json = json.dumps(
            {
                "root_cause": True,
                "discard_justification": None,
                "confounded_by": None,
                "medical_reasoning": "Known trigger with medical evidence",
            }
        )
        mock_response = create_mock_response(response_json[1:])
        claude_service.client.messages.create.return_value = mock_response

        ingredient_data = {
            "ingredient_name": "onion",
            "confidence_level": "high",
            "times_eaten": 5,
            "total_symptom_occurrences": 4,
            "associated_symptoms": [{"name": "bloating", "frequency": 4}],
        }

        result = await claude_service.classify_root_cause(ingredient_data, [], "")

        assert result["root_cause"] is True
        assert result["confounded_by"] is None

    @pytest.mark.asyncio
    async def test_identifies_confounder(self, claude_service):
        """Test that confounder is correctly identified."""
        response_json = json.dumps(
            {
                "root_cause": False,
                "discard_justification": "High co-occurrence with known trigger",
                "confounded_by": "onion",
                "medical_reasoning": "Garlic often eaten with onion, which is the likely trigger",
            }
        )
        mock_response = create_mock_response(response_json[1:])
        claude_service.client.messages.create.return_value = mock_response

        ingredient_data = {
            "ingredient_name": "garlic",
            "confidence_level": "high",
            "times_eaten": 5,
            "total_symptom_occurrences": 4,
            "associated_symptoms": [{"name": "bloating", "frequency": 4}],
        }
        cooccurrence_data = [
            {
                "with_ingredient_name": "onion",
                "conditional_probability": 0.95,
                "cooccurrence_meals": 5,
            }
        ]

        result = await claude_service.classify_root_cause(
            ingredient_data, cooccurrence_data, ""
        )

        assert result["root_cause"] is False
        assert result["confounded_by"] == "onion"

    @pytest.mark.asyncio
    async def test_handles_trailing_commas(self, claude_service):
        """Test that trailing commas in JSON are handled."""
        # JSON with trailing comma (common AI error)
        response_json = """"root_cause": true,
            "discard_justification": null,
            "confounded_by": null,
            "medical_reasoning": "Test",
        }"""
        mock_response = create_mock_response(response_json)
        claude_service.client.messages.create.return_value = mock_response

        result = await claude_service.classify_root_cause(
            {"ingredient_name": "test", "associated_symptoms": []}, [], ""
        )

        assert result["root_cause"] is True


# =============================================================================
# Pattern Analysis Tests
# =============================================================================


class TestAnalyzePatterns:
    """Tests for analyze_patterns method."""

    @pytest.mark.asyncio
    async def test_basic_pattern_analysis(self, claude_service):
        """Test basic pattern analysis."""
        claude_service.client.messages.create.return_value = create_mock_response(
            "## Analysis\n\nPotential correlation found between dairy and bloating.",
            {"input_tokens": 2000, "cache_read_input_tokens": 0},
        )

        result = await claude_service.analyze_patterns(
            "Meal data here...", "Symptom data here...", "Find correlations"
        )

        assert "analysis" in result
        assert "model" in result
        assert "cache_hit" in result
        assert result["cache_hit"] is False

    @pytest.mark.asyncio
    async def test_pattern_analysis_with_cache_hit(self, claude_service):
        """Test pattern analysis with cache hit."""
        claude_service.client.messages.create.return_value = create_mock_response(
            "Cached analysis result",
            {"input_tokens": 2000, "cache_read_input_tokens": 1800},
        )

        result = await claude_service.analyze_patterns("meals", "symptoms")

        assert result["cache_hit"] is True
        assert result["cached_tokens"] == 1800


# =============================================================================
# Helper Method Tests
# =============================================================================


class TestHelperMethods:
    """Tests for helper methods."""

    def test_get_media_type_jpeg(self, claude_service):
        """Test media type detection for JPEG."""
        assert claude_service._get_media_type("/path/to/image.jpg") == "image/jpeg"
        assert claude_service._get_media_type("/path/to/image.jpeg") == "image/jpeg"

    def test_get_media_type_png(self, claude_service):
        """Test media type detection for PNG."""
        assert claude_service._get_media_type("/path/to/image.png") == "image/png"

    def test_get_media_type_gif(self, claude_service):
        """Test media type detection for GIF."""
        assert claude_service._get_media_type("/path/to/image.gif") == "image/gif"

    def test_get_media_type_webp(self, claude_service):
        """Test media type detection for WebP."""
        assert claude_service._get_media_type("/path/to/image.webp") == "image/webp"

    def test_get_media_type_unknown(self, claude_service):
        """Test media type detection for unknown extension defaults to JPEG."""
        assert claude_service._get_media_type("/path/to/image.bmp") == "image/jpeg"

    def test_load_image_base64(self, claude_service, sample_image_file):
        """Test image loading and base64 encoding."""
        result = claude_service._load_image_base64(sample_image_file)
        assert isinstance(result, str)
        # Should be valid base64
        import base64

        decoded = base64.b64decode(result)
        assert len(decoded) > 0

    def test_format_correlation_data(self, claude_service):
        """Test formatting of correlation data."""
        data = [
            {
                "ingredient_name": "onion",
                "state": "raw",
                "times_eaten": 5,
                "total_symptom_occurrences": 4,
                "immediate_total": 3,
                "delayed_total": 1,
                "cumulative_total": 0,
                "associated_symptoms": [
                    {
                        "name": "bloating",
                        "severity_avg": 7.0,
                        "frequency": 4,
                        "lag_hours": 1.5,
                    }
                ],
            }
        ]

        result = claude_service._format_correlation_data(data)

        assert "onion" in result
        assert "Times eaten: 5" in result
        assert "bloating" in result

    def test_format_single_ingredient_data(self, claude_service):
        """Test formatting of single ingredient data."""
        data = {
            "ingredient_name": "milk",
            "state": "processed",
            "times_eaten": 10,
            "total_symptom_occurrences": 8,
            "immediate_total": 2,
            "delayed_total": 6,
            "cumulative_total": 0,
            "confidence_level": "high",
            "associated_symptoms": [
                {"name": "gas", "severity_avg": 6.0, "frequency": 8, "lag_hours": 6.0}
            ],
        }

        result = claude_service._format_single_ingredient_data(data)

        assert "milk" in result
        assert "10 times" in result
        assert "gas" in result

    def test_format_meal_history_empty(self, claude_service):
        """Test formatting empty meal history."""
        result = claude_service._format_meal_history([])
        assert "No meal history available" in result

    def test_format_meal_history(self, claude_service):
        """Test formatting meal history."""
        meals = [
            {"name": "Breakfast", "ingredients": [{"name": "eggs"}, {"name": "toast"}]},
            {"name": "Lunch", "ingredients": [{"name": "salad"}]},
        ]

        result = claude_service._format_meal_history(meals)

        assert "Breakfast" in result
        assert "eggs" in result
        assert "Lunch" in result

    def test_format_root_cause_input(self, claude_service):
        """Test formatting root cause classification input."""
        ingredient_data = {
            "ingredient_name": "garlic",
            "times_eaten": 5,
            "total_symptom_occurrences": 4,
            "confidence_level": "high",
            "associated_symptoms": [{"name": "bloating", "frequency": 4}],
        }
        cooccurrence_data = [
            {
                "with_ingredient_name": "onion",
                "conditional_probability": 0.9,
                "cooccurrence_meals": 4,
            }
        ]

        result = claude_service._format_root_cause_input(
            ingredient_data, cooccurrence_data, "Medical context here"
        )

        assert "garlic" in result
        assert "onion" in result
        assert "almost always" in result or "usually" in result
        assert "Medical context here" in result

    def test_format_root_cause_input_no_cooccurrence(self, claude_service):
        """Test formatting root cause input without co-occurrence data."""
        ingredient_data = {
            "ingredient_name": "onion",
            "times_eaten": 5,
            "total_symptom_occurrences": 4,
            "confidence_level": "high",
            "associated_symptoms": [],
        }

        result = claude_service._format_root_cause_input(ingredient_data, [], "")

        assert "doesn't frequently appear" in result

    def test_estimate_request_tokens(self, claude_service):
        """Test token estimation."""
        data = "Test data " * 100  # ~1000 characters
        prompt = "System prompt " * 50  # ~700 characters

        tokens = claude_service._estimate_request_tokens(data, prompt)

        # Rough estimate: ~4 chars per token
        assert 400 <= tokens <= 500

    def test_validate_request_size_valid(self, claude_service):
        """Test request size validation passes for valid requests."""
        data = "Small data"
        prompt = "Small prompt"

        # Should not raise
        claude_service._validate_request_size(data, prompt)

    def test_validate_request_size_too_large(self, claude_service):
        """Test request size validation fails for large requests."""
        data = "x" * 500000  # Very large data
        prompt = "System prompt"

        with pytest.raises(ValueError, match="Request too large"):
            claude_service._validate_request_size(data, prompt, max_tokens=1000)


# =============================================================================
# Ongoing Symptom Detection Tests
# =============================================================================


class TestDetectOngoingSymptom:
    """Tests for detect_ongoing_symptom method."""

    @pytest.mark.asyncio
    async def test_ongoing_symptom_detected(self, claude_service):
        """Test that ongoing symptom is detected."""
        response_json = json.dumps(
            {
                "is_continuation": True,
                "confidence": 0.9,
                "reasoning": "Same symptom type continuing",
            }
        )
        claude_service.client.messages.create.return_value = create_mock_response(
            response_json
        )

        previous = {
            "name": "bloating",
            "severity": 6,
            "start_time": datetime.now(timezone.utc),
            "end_time": None,
        }
        current = {
            "name": "bloating",
            "severity": 5,
            "time": datetime.now(timezone.utc),
        }

        result = await claude_service.detect_ongoing_symptom(previous, current)

        assert result["is_ongoing"] is True

    @pytest.mark.asyncio
    async def test_ongoing_symptom_not_detected(self, claude_service):
        """Test that non-ongoing symptom is detected."""
        response_json = json.dumps(
            {
                "is_continuation": False,
                "confidence": 0.2,
                "reasoning": "Different symptom",
            }
        )
        claude_service.client.messages.create.return_value = create_mock_response(
            response_json
        )

        previous = {
            "name": "bloating",
            "severity": 6,
            "start_time": datetime.now(timezone.utc),
            "end_time": None,
        }
        current = {
            "name": "headache",
            "severity": 5,
            "time": datetime.now(timezone.utc),
        }

        result = await claude_service.detect_ongoing_symptom(previous, current)

        assert result["is_ongoing"] is False

    @pytest.mark.asyncio
    async def test_json_in_plain_code_block(self, claude_service):
        """Test parsing JSON in plain code block."""
        response = """```
{"is_continuation": true, "confidence": 0.85, "reasoning": "Similar"}
```"""
        claude_service.client.messages.create.return_value = create_mock_response(
            response
        )

        result = await claude_service.detect_ongoing_symptom(
            {
                "name": "test",
                "severity": 5,
                "start_time": datetime.now(timezone.utc),
                "end_time": None,
            },
            {"name": "test", "severity": 4, "time": datetime.now(timezone.utc)},
        )

        assert result["is_ongoing"] is True

    @pytest.mark.asyncio
    async def test_error_handling(self, claude_service):
        """Test error handling in ongoing detection."""
        claude_service.client.messages.create.side_effect = Exception("API Error")

        with pytest.raises(ValueError, match="AI ongoing detection failed"):
            await claude_service.detect_ongoing_symptom(
                {
                    "name": "test",
                    "severity": 5,
                    "start_time": datetime.now(timezone.utc),
                    "end_time": None,
                },
                {"name": "test", "severity": 4, "time": datetime.now(timezone.utc)},
            )

    @pytest.mark.asyncio
    async def test_json_in_markdown_block(self, claude_service):
        """Test parsing JSON wrapped in json code block."""
        response = """```json
{"is_continuation": true, "confidence": 0.85, "reasoning": "Similar"}
```"""
        claude_service.client.messages.create.return_value = create_mock_response(
            response
        )

        result = await claude_service.detect_ongoing_symptom(
            {
                "name": "test",
                "severity": 5,
                "start_time": datetime.now(timezone.utc),
                "end_time": None,
            },
            {"name": "test", "severity": 4, "time": datetime.now(timezone.utc)},
        )

        assert result["is_ongoing"] is True

    @pytest.mark.asyncio
    async def test_invalid_json_raises_error(self, claude_service):
        """Test that invalid JSON raises ValueError."""
        claude_service.client.messages.create.return_value = create_mock_response(
            "Not valid JSON at all"
        )

        with pytest.raises(ValueError, match="parse"):
            await claude_service.detect_ongoing_symptom(
                {
                    "name": "test",
                    "severity": 5,
                    "start_time": datetime.now(timezone.utc),
                    "end_time": None,
                },
                {"name": "test", "severity": 4, "time": datetime.now(timezone.utc)},
            )


# =============================================================================
# Additional Error Handling Tests
# =============================================================================


class TestValidateMealImageErrors:
    """Additional error handling tests for validate_meal_image."""

    @pytest.mark.asyncio
    async def test_generic_exception(self, claude_service, sample_image_file):
        """Test that generic exceptions are wrapped in ValueError."""
        claude_service.client.messages.create.side_effect = Exception(
            "Unexpected error"
        )

        with pytest.raises(ValueError, match="validation failed"):
            await claude_service.validate_meal_image(sample_image_file)


class TestAnalyzeMealImageErrors:
    """Additional error handling tests for analyze_meal_image."""

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, claude_service, sample_image_file):
        """Test that RateLimitError is raised on rate limiting."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        claude_service.client.messages.create.side_effect = anthropic.RateLimitError(
            message="Rate limited", response=mock_response, body={}
        )

        with pytest.raises(RateLimitError):
            await claude_service.analyze_meal_image(sample_image_file)

    @pytest.mark.asyncio
    async def test_server_error(self, claude_service, sample_image_file):
        """Test that 5xx errors raise ServiceUnavailableError."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        claude_service.client.messages.create.side_effect = anthropic.APIStatusError(
            message="Server error", response=mock_response, body={}
        )

        with pytest.raises(ServiceUnavailableError):
            await claude_service.analyze_meal_image(sample_image_file)

    @pytest.mark.asyncio
    async def test_client_error(self, claude_service, sample_image_file):
        """Test that 4xx errors raise ValueError."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        claude_service.client.messages.create.side_effect = anthropic.APIStatusError(
            message="Bad request", response=mock_response, body={}
        )

        with pytest.raises(ValueError, match="Request error"):
            await claude_service.analyze_meal_image(sample_image_file)

    @pytest.mark.asyncio
    async def test_json_decode_error(self, claude_service, sample_image_file):
        """Test that JSONDecodeError is wrapped in ValueError."""
        claude_service.client.messages.create.return_value = create_mock_response(
            "This is not valid JSON {["
        )

        with pytest.raises(ValueError, match="parse"):
            await claude_service.analyze_meal_image(sample_image_file)


class TestClarifySymptomErrors:
    """Error handling tests for clarify_symptom."""

    @pytest.mark.asyncio
    async def test_connection_error(self, claude_service):
        """Test that APIConnectionError raises ServiceUnavailableError."""
        claude_service.client.messages.create.side_effect = (
            anthropic.APIConnectionError(request=MagicMock())
        )

        with pytest.raises(ServiceUnavailableError):
            await claude_service.clarify_symptom("I feel sick")

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, claude_service):
        """Test that RateLimitError is raised."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        claude_service.client.messages.create.side_effect = anthropic.RateLimitError(
            message="Rate limited", response=mock_response, body={}
        )

        with pytest.raises(RateLimitError):
            await claude_service.clarify_symptom("stomach pain")

    @pytest.mark.asyncio
    async def test_server_error(self, claude_service):
        """Test that 5xx errors raise ServiceUnavailableError."""
        mock_response = MagicMock()
        mock_response.status_code = 503
        claude_service.client.messages.create.side_effect = anthropic.APIStatusError(
            message="Service unavailable", response=mock_response, body={}
        )

        with pytest.raises(ServiceUnavailableError):
            await claude_service.clarify_symptom("nausea")

    @pytest.mark.asyncio
    async def test_client_error(self, claude_service):
        """Test that 4xx errors raise ValueError."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        claude_service.client.messages.create.side_effect = anthropic.APIStatusError(
            message="Bad request", response=mock_response, body={}
        )

        with pytest.raises(ValueError, match="Request error"):
            await claude_service.clarify_symptom("test")


class TestElaborateSymptomTagsErrors:
    """Error handling tests for elaborate_symptom_tags."""

    @pytest.mark.asyncio
    async def test_connection_error(self, claude_service):
        """Test that APIConnectionError raises ServiceUnavailableError."""
        claude_service.client.messages.create.side_effect = (
            anthropic.APIConnectionError(request=MagicMock())
        )

        tags = [{"name": "bloating", "severity": 5}]
        with pytest.raises(ServiceUnavailableError):
            await claude_service.elaborate_symptom_tags(tags)

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, claude_service):
        """Test that RateLimitError is raised."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        claude_service.client.messages.create.side_effect = anthropic.RateLimitError(
            message="Rate limited", response=mock_response, body={}
        )

        tags = [{"name": "gas", "severity": 4}]
        with pytest.raises(RateLimitError):
            await claude_service.elaborate_symptom_tags(tags)

    @pytest.mark.asyncio
    async def test_server_error(self, claude_service):
        """Test that 5xx errors raise ServiceUnavailableError."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        claude_service.client.messages.create.side_effect = anthropic.APIStatusError(
            message="Server error", response=mock_response, body={}
        )

        tags = [{"name": "nausea", "severity": 6}]
        with pytest.raises(ServiceUnavailableError):
            await claude_service.elaborate_symptom_tags(tags)


class TestDetectEpisodeContinuationErrors:
    """Error handling tests for detect_episode_continuation."""

    @pytest.mark.asyncio
    async def test_connection_error(self, claude_service):
        """Test that APIConnectionError raises ServiceUnavailableError."""
        claude_service.client.messages.create.side_effect = (
            anthropic.APIConnectionError(request=MagicMock())
        )

        with pytest.raises(ServiceUnavailableError):
            await claude_service.detect_episode_continuation(
                [{"name": "test", "severity": 5}],
                datetime.now(timezone.utc),
                {
                    "tags": [],
                    "start_time": datetime.now(timezone.utc),
                    "end_time": None,
                    "notes": None,
                },
            )

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, claude_service):
        """Test that RateLimitError is raised."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        claude_service.client.messages.create.side_effect = anthropic.RateLimitError(
            message="Rate limited", response=mock_response, body={}
        )

        with pytest.raises(RateLimitError):
            await claude_service.detect_episode_continuation(
                [{"name": "test", "severity": 5}],
                datetime.now(timezone.utc),
                {
                    "tags": [],
                    "start_time": datetime.now(timezone.utc),
                    "end_time": None,
                    "notes": None,
                },
            )

    @pytest.mark.asyncio
    async def test_server_error(self, claude_service):
        """Test that 5xx errors raise ServiceUnavailableError."""
        mock_response = MagicMock()
        mock_response.status_code = 502
        claude_service.client.messages.create.side_effect = anthropic.APIStatusError(
            message="Bad gateway", response=mock_response, body={}
        )

        with pytest.raises(ServiceUnavailableError):
            await claude_service.detect_episode_continuation(
                [{"name": "test", "severity": 5}],
                datetime.now(timezone.utc),
                {
                    "tags": [],
                    "start_time": datetime.now(timezone.utc),
                    "end_time": None,
                    "notes": None,
                },
            )

    @pytest.mark.asyncio
    async def test_client_error(self, claude_service):
        """Test that 4xx errors raise ValueError."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        claude_service.client.messages.create.side_effect = anthropic.APIStatusError(
            message="Bad request", response=mock_response, body={}
        )

        with pytest.raises(ValueError, match="Request error"):
            await claude_service.detect_episode_continuation(
                [{"name": "test", "severity": 5}],
                datetime.now(timezone.utc),
                {
                    "tags": [],
                    "start_time": datetime.now(timezone.utc),
                    "end_time": None,
                    "notes": None,
                },
            )

    @pytest.mark.asyncio
    async def test_json_in_plain_code_block(self, claude_service):
        """Test parsing JSON in plain code block."""
        response = """```
{"is_continuation": false, "confidence": 0.3, "reasoning": "Different"}
```"""
        claude_service.client.messages.create.return_value = create_mock_response(
            response
        )

        result = await claude_service.detect_episode_continuation(
            [{"name": "test", "severity": 5}],
            datetime.now(timezone.utc),
            {
                "tags": [],
                "start_time": datetime.now(timezone.utc),
                "end_time": None,
                "notes": None,
            },
        )

        assert result["is_continuation"] is False

    @pytest.mark.asyncio
    async def test_json_decode_error(self, claude_service):
        """Test that JSONDecodeError is wrapped in ValueError."""
        claude_service.client.messages.create.return_value = create_mock_response(
            "Invalid JSON here!"
        )

        with pytest.raises(ValueError, match="parse"):
            await claude_service.detect_episode_continuation(
                [{"name": "test", "severity": 5}],
                datetime.now(timezone.utc),
                {
                    "tags": [],
                    "start_time": datetime.now(timezone.utc),
                    "end_time": None,
                    "notes": None,
                },
            )


class TestAnalyzePatternsErrors:
    """Error handling tests for analyze_patterns."""

    @pytest.mark.asyncio
    async def test_connection_error(self, claude_service):
        """Test that APIConnectionError raises ServiceUnavailableError."""
        claude_service.client.messages.create.side_effect = (
            anthropic.APIConnectionError(request=MagicMock())
        )

        with pytest.raises(ServiceUnavailableError):
            await claude_service.analyze_patterns("meals", "symptoms")

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, claude_service):
        """Test that RateLimitError is raised."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        claude_service.client.messages.create.side_effect = anthropic.RateLimitError(
            message="Rate limited", response=mock_response, body={}
        )

        with pytest.raises(RateLimitError):
            await claude_service.analyze_patterns("meals", "symptoms")

    @pytest.mark.asyncio
    async def test_server_error(self, claude_service):
        """Test that 5xx errors raise ServiceUnavailableError."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        claude_service.client.messages.create.side_effect = anthropic.APIStatusError(
            message="Server error", response=mock_response, body={}
        )

        with pytest.raises(ServiceUnavailableError):
            await claude_service.analyze_patterns("meals", "symptoms")

    @pytest.mark.asyncio
    async def test_client_error(self, claude_service):
        """Test that 4xx errors raise ValueError."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        claude_service.client.messages.create.side_effect = anthropic.APIStatusError(
            message="Bad request", response=mock_response, body={}
        )

        with pytest.raises(ValueError, match="Request error"):
            await claude_service.analyze_patterns("meals", "symptoms")


class TestDiagnoseCorrelationsErrors:
    """Error handling tests for diagnose_correlations."""

    @pytest.mark.asyncio
    async def test_empty_response_content(self, claude_service):
        """Test handling of empty response content."""
        mock_response = MagicMock()
        mock_response.content = []  # Empty content
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 100
        claude_service.client.messages.create.return_value = mock_response

        with pytest.raises(ValueError, match="No text content"):
            await claude_service.diagnose_correlations([])

    @pytest.mark.asyncio
    async def test_json_decode_error(self, claude_service):
        """Test that JSONDecodeError is wrapped in ValueError."""
        mock_response = create_mock_response("Invalid JSON {{{{")
        claude_service.client.messages.create.return_value = mock_response

        with pytest.raises(ValueError, match="Invalid JSON"):
            await claude_service.diagnose_correlations([])

    @pytest.mark.asyncio
    async def test_connection_error(self, claude_service):
        """Test that APIConnectionError raises ServiceUnavailableError."""
        claude_service.client.messages.create.side_effect = (
            anthropic.APIConnectionError(request=MagicMock())
        )

        with pytest.raises(ServiceUnavailableError):
            await claude_service.diagnose_correlations([])

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, claude_service):
        """Test that RateLimitError is raised."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        claude_service.client.messages.create.side_effect = anthropic.RateLimitError(
            message="Rate limited", response=mock_response, body={}
        )

        with pytest.raises(RateLimitError):
            await claude_service.diagnose_correlations([])

    @pytest.mark.asyncio
    async def test_server_error(self, claude_service):
        """Test that 5xx errors raise ServiceUnavailableError."""
        mock_response = MagicMock()
        mock_response.status_code = 503
        claude_service.client.messages.create.side_effect = anthropic.APIStatusError(
            message="Service unavailable", response=mock_response, body={}
        )

        with pytest.raises(ServiceUnavailableError):
            await claude_service.diagnose_correlations([])


class TestDiagnoseSingleIngredientErrors:
    """Error handling tests for diagnose_single_ingredient."""

    @pytest.mark.asyncio
    async def test_empty_response_content(self, claude_service):
        """Test handling of empty response content."""
        mock_response = MagicMock()
        mock_response.content = []
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 100
        claude_service.client.messages.create.return_value = mock_response

        ingredient_data = {"ingredient_name": "test", "associated_symptoms": []}
        with pytest.raises(ValueError, match="No text content"):
            await claude_service.diagnose_single_ingredient(ingredient_data, [])

    @pytest.mark.asyncio
    async def test_json_decode_error(self, claude_service):
        """Test that JSONDecodeError is wrapped in ValueError."""
        mock_response = create_mock_response("Invalid JSON!!!!")
        claude_service.client.messages.create.return_value = mock_response

        ingredient_data = {"ingredient_name": "test", "associated_symptoms": []}
        with pytest.raises(ValueError, match="Invalid JSON"):
            await claude_service.diagnose_single_ingredient(ingredient_data, [])

    @pytest.mark.asyncio
    async def test_connection_error(self, claude_service):
        """Test that APIConnectionError raises ServiceUnavailableError."""
        claude_service.client.messages.create.side_effect = (
            anthropic.APIConnectionError(request=MagicMock())
        )

        ingredient_data = {"ingredient_name": "test", "associated_symptoms": []}
        with pytest.raises(ServiceUnavailableError):
            await claude_service.diagnose_single_ingredient(ingredient_data, [])

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, claude_service):
        """Test that RateLimitError is raised."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        claude_service.client.messages.create.side_effect = anthropic.RateLimitError(
            message="Rate limited", response=mock_response, body={}
        )

        ingredient_data = {"ingredient_name": "test", "associated_symptoms": []}
        with pytest.raises(RateLimitError):
            await claude_service.diagnose_single_ingredient(ingredient_data, [])

    @pytest.mark.asyncio
    async def test_server_error(self, claude_service):
        """Test that 5xx errors raise ServiceUnavailableError."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        claude_service.client.messages.create.side_effect = anthropic.APIStatusError(
            message="Server error", response=mock_response, body={}
        )

        ingredient_data = {"ingredient_name": "test", "associated_symptoms": []}
        with pytest.raises(ServiceUnavailableError):
            await claude_service.diagnose_single_ingredient(ingredient_data, [])


class TestClassifyRootCauseErrors:
    """Error handling tests for classify_root_cause."""

    @pytest.mark.asyncio
    async def test_empty_response_content(self, claude_service):
        """Test handling of empty response content."""
        mock_response = MagicMock()
        mock_response.content = []
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 100
        claude_service.client.messages.create.return_value = mock_response

        ingredient_data = {"ingredient_name": "test", "associated_symptoms": []}
        with pytest.raises(ValueError, match="No text content"):
            await claude_service.classify_root_cause(ingredient_data, [], "")

    @pytest.mark.asyncio
    async def test_json_decode_error(self, claude_service):
        """Test that JSONDecodeError is wrapped in ValueError."""
        mock_response = create_mock_response("Invalid JSON content")
        claude_service.client.messages.create.return_value = mock_response

        ingredient_data = {"ingredient_name": "test", "associated_symptoms": []}
        with pytest.raises(ValueError, match="Invalid JSON"):
            await claude_service.classify_root_cause(ingredient_data, [], "")

    @pytest.mark.asyncio
    async def test_connection_error(self, claude_service):
        """Test that APIConnectionError raises ServiceUnavailableError."""
        claude_service.client.messages.create.side_effect = (
            anthropic.APIConnectionError(request=MagicMock())
        )

        ingredient_data = {"ingredient_name": "test", "associated_symptoms": []}
        with pytest.raises(ServiceUnavailableError):
            await claude_service.classify_root_cause(ingredient_data, [], "")

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, claude_service):
        """Test that RateLimitError is raised."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        claude_service.client.messages.create.side_effect = anthropic.RateLimitError(
            message="Rate limited", response=mock_response, body={}
        )

        ingredient_data = {"ingredient_name": "test", "associated_symptoms": []}
        with pytest.raises(RateLimitError):
            await claude_service.classify_root_cause(ingredient_data, [], "")

    @pytest.mark.asyncio
    async def test_server_error(self, claude_service):
        """Test that 5xx errors raise ServiceUnavailableError."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        claude_service.client.messages.create.side_effect = anthropic.APIStatusError(
            message="Server error", response=mock_response, body={}
        )

        ingredient_data = {"ingredient_name": "test", "associated_symptoms": []}
        with pytest.raises(ServiceUnavailableError):
            await claude_service.classify_root_cause(ingredient_data, [], "")
