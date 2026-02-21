"""
Unit tests for AI schema validation and conversational retry logic.

Tests the Pydantic schema models and _call_with_schema_retry() helper
directly, using mocked Claude API responses.
"""

import json

import pytest
from unittest.mock import MagicMock, patch
from pydantic import ValidationError

from app.services.ai_schemas import (
    MealAnalysisSchema,
    ClarifySymptomQuestionSchema,
    ClarifySymptomCompleteSchema,
    ClarifySymptomSchema,
    EpisodeContinuationSchema,
    DiagnosisCorrelationsSchema,
    SingleIngredientDiagnosisSchema,
    AlternativeMealSchema,
    RootCauseSchema,
    CitationSchema,
)
from app.services.ai_service import (
    _strip_markdown_json,
    _fix_trailing_commas,
)


# =============================================================================
# Schema Validation Tests
# =============================================================================


class TestMealAnalysisSchema:
    def test_valid_meal(self):
        data = {
            "meal_name": "Chicken Salad",
            "ingredients": [
                {
                    "name": "chicken",
                    "state": "cooked",
                    "quantity": "150g",
                    "confidence": 0.9,
                }
            ],
        }
        result = MealAnalysisSchema.model_validate(data)
        assert result.meal_name == "Chicken Salad"
        assert len(result.ingredients) == 1
        assert result.ingredients[0].confidence == 0.9

    def test_valid_meal_default_quantity(self):
        data = {
            "meal_name": "Toast",
            "ingredients": [{"name": "bread", "state": "cooked", "confidence": 0.8}],
        }
        result = MealAnalysisSchema.model_validate(data)
        assert result.ingredients[0].quantity == ""

    def test_missing_meal_name_uses_default(self):
        data = {
            "ingredients": [{"name": "bread", "state": "cooked", "confidence": 0.8}]
        }
        result = MealAnalysisSchema.model_validate(data)
        assert result.meal_name == "Untitled Meal"

    def test_missing_ingredients(self):
        data = {"meal_name": "Toast"}
        with pytest.raises(ValidationError):
            MealAnalysisSchema.model_validate(data)

    def test_confidence_out_of_range(self):
        data = {
            "meal_name": "Toast",
            "ingredients": [{"name": "bread", "state": "cooked", "confidence": 1.5}],
        }
        with pytest.raises(ValidationError):
            MealAnalysisSchema.model_validate(data)

    def test_confidence_negative(self):
        data = {
            "meal_name": "Toast",
            "ingredients": [{"name": "bread", "state": "cooked", "confidence": -0.1}],
        }
        with pytest.raises(ValidationError):
            MealAnalysisSchema.model_validate(data)

    def test_empty_ingredients_list(self):
        data = {"meal_name": "Empty Plate", "ingredients": []}
        result = MealAnalysisSchema.model_validate(data)
        assert len(result.ingredients) == 0

    def test_ingredient_missing_name(self):
        data = {
            "meal_name": "Toast",
            "ingredients": [{"state": "cooked", "confidence": 0.8}],
        }
        with pytest.raises(ValidationError):
            MealAnalysisSchema.model_validate(data)


class TestClarifySymptomSchema:
    def test_question_mode(self):
        from pydantic import TypeAdapter

        adapter = TypeAdapter(ClarifySymptomSchema)
        data = {"mode": "question", "question": "When did symptoms start?"}
        result = adapter.validate_python(data)
        assert isinstance(result, ClarifySymptomQuestionSchema)
        assert result.mode == "question"
        assert result.question == "When did symptoms start?"

    def test_complete_mode(self):
        from pydantic import TypeAdapter

        adapter = TypeAdapter(ClarifySymptomSchema)
        data = {
            "mode": "complete",
            "structured": {"type": "bloating", "severity": 6, "notes": "After dinner"},
        }
        result = adapter.validate_python(data)
        assert isinstance(result, ClarifySymptomCompleteSchema)
        assert result.mode == "complete"
        assert result.structured.type == "bloating"
        assert result.structured.severity == 6

    def test_invalid_mode(self):
        from pydantic import TypeAdapter

        adapter = TypeAdapter(ClarifySymptomSchema)
        data = {"mode": "invalid", "question": "What?"}
        with pytest.raises(ValidationError):
            adapter.validate_python(data)

    def test_severity_out_of_range(self):
        from pydantic import TypeAdapter

        adapter = TypeAdapter(ClarifySymptomSchema)
        data = {
            "mode": "complete",
            "structured": {"type": "bloating", "severity": 11, "notes": "Bad"},
        }
        with pytest.raises(ValidationError):
            adapter.validate_python(data)

    def test_severity_zero(self):
        from pydantic import TypeAdapter

        adapter = TypeAdapter(ClarifySymptomSchema)
        data = {
            "mode": "complete",
            "structured": {"type": "bloating", "severity": 0, "notes": "Nothing"},
        }
        with pytest.raises(ValidationError):
            adapter.validate_python(data)


class TestEpisodeContinuationSchema:
    def test_valid(self):
        data = {
            "is_continuation": True,
            "confidence": 0.85,
            "reasoning": "Same symptom type within episode window.",
        }
        result = EpisodeContinuationSchema.model_validate(data)
        assert result.is_continuation is True
        assert result.confidence == 0.85

    def test_missing_reasoning(self):
        data = {"is_continuation": True, "confidence": 0.85}
        with pytest.raises(ValidationError):
            EpisodeContinuationSchema.model_validate(data)

    def test_confidence_out_of_range(self):
        data = {
            "is_continuation": False,
            "confidence": 1.1,
            "reasoning": "Different.",
        }
        with pytest.raises(ValidationError):
            EpisodeContinuationSchema.model_validate(data)


class TestDiagnosisCorrelationsSchema:
    def test_valid_with_analyses(self):
        data = {
            "ingredient_analyses": [
                {
                    "ingredient_name": "onion",
                    "medical_context": "Known irritant",
                    "citations": [
                        {
                            "url": "https://example.com",
                            "title": "Study",
                            "source_type": "journal",
                            "snippet": "Data",
                        }
                    ],
                }
            ],
            "overall_summary": "Analysis complete.",
            "caveats": ["Correlation, not causation."],
        }
        result = DiagnosisCorrelationsSchema.model_validate(data)
        assert len(result.ingredient_analyses) == 1
        assert result.ingredient_analyses[0].ingredient_name == "onion"

    def test_empty_analyses(self):
        data = {"ingredient_analyses": []}
        result = DiagnosisCorrelationsSchema.model_validate(data)
        assert len(result.ingredient_analyses) == 0

    def test_missing_ingredient_name(self):
        data = {"ingredient_analyses": [{"medical_context": "Known irritant"}]}
        with pytest.raises(ValidationError):
            DiagnosisCorrelationsSchema.model_validate(data)

    def test_defaults(self):
        data = {
            "ingredient_analyses": [{"ingredient_name": "milk"}],
        }
        result = DiagnosisCorrelationsSchema.model_validate(data)
        assert result.overall_summary == ""
        assert result.caveats == []


class TestSingleIngredientDiagnosisSchema:
    def test_valid(self):
        data = {
            "diagnosis_summary": "Milk shows correlation.",
            "recommendations_summary": "Try elimination diet.",
            "processing_suggestions": {
                "cooked_vs_raw": "Cooking may help.",
                "alternatives": ["oat milk"],
            },
            "alternative_meals": [
                {"meal_id": 1, "name": "Oat Bowl", "reason": "No dairy"}
            ],
            "citations": [],
        }
        result = SingleIngredientDiagnosisSchema.model_validate(data)
        assert result.diagnosis_summary == "Milk shows correlation."
        assert len(result.alternative_meals) == 1

    def test_minimal(self):
        data = {
            "diagnosis_summary": "Summary.",
            "recommendations_summary": "Recommendations.",
        }
        result = SingleIngredientDiagnosisSchema.model_validate(data)
        assert result.processing_suggestions is None
        assert result.alternative_meals == []

    def test_missing_required(self):
        data = {"diagnosis_summary": "Summary."}
        with pytest.raises(ValidationError):
            SingleIngredientDiagnosisSchema.model_validate(data)


class TestRootCauseSchema:
    def test_valid_root_cause(self):
        data = {
            "root_cause": True,
            "medical_reasoning": "Strong evidence.",
        }
        result = RootCauseSchema.model_validate(data)
        assert result.root_cause is True
        assert result.discard_justification is None
        assert result.confounded_by is None

    def test_valid_confounder(self):
        data = {
            "root_cause": False,
            "discard_justification": "High co-occurrence with onion.",
            "confounded_by": "onion",
            "medical_reasoning": "Garlic and onion co-occur.",
        }
        result = RootCauseSchema.model_validate(data)
        assert result.root_cause is False
        assert result.confounded_by == "onion"

    def test_missing_medical_reasoning(self):
        data = {"root_cause": True}
        with pytest.raises(ValidationError):
            RootCauseSchema.model_validate(data)


class TestCitationSchema:
    def test_valid(self):
        data = {
            "url": "https://pubmed.ncbi.nlm.nih.gov/12345/",
            "title": "Study on food intolerance",
            "source_type": "medical_journal",
            "snippet": "Results show...",
            "relevance": 0.9,
        }
        result = CitationSchema.model_validate(data)
        assert result.relevance == 0.9

    def test_default_relevance(self):
        data = {
            "url": "https://example.com",
            "title": "Title",
            "source_type": "web",
            "snippet": "Text",
        }
        result = CitationSchema.model_validate(data)
        assert result.relevance == 0.5


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestStripMarkdownJson:
    def test_json_code_block(self):
        text = '```json\n{"key": "value"}\n```'
        assert _strip_markdown_json(text) == '{"key": "value"}'

    def test_generic_code_block(self):
        text = '```\n{"key": "value"}\n```'
        assert _strip_markdown_json(text) == '{"key": "value"}'

    def test_no_code_block(self):
        text = '{"key": "value"}'
        assert _strip_markdown_json(text) == '{"key": "value"}'

    def test_json_block_with_surrounding_text(self):
        text = 'Here is the result:\n```json\n{"key": "value"}\n```\nDone.'
        assert _strip_markdown_json(text) == '{"key": "value"}'

    def test_empty_code_block(self):
        text = "```json\n\n```"
        assert _strip_markdown_json(text) == ""


class TestFixTrailingCommas:
    def test_trailing_comma_in_object(self):
        assert _fix_trailing_commas('{"a": 1,}') == '{"a": 1}'

    def test_trailing_comma_in_array(self):
        assert _fix_trailing_commas("[1, 2, 3,]") == "[1, 2, 3]"

    def test_trailing_comma_with_whitespace(self):
        assert _fix_trailing_commas('{"a": 1 , }') == '{"a": 1 }'

    def test_no_trailing_comma(self):
        assert _fix_trailing_commas('{"a": 1}') == '{"a": 1}'

    def test_nested_trailing_commas(self):
        text = '{"a": [1, 2,], "b": {"c": 3,},}'
        result = _fix_trailing_commas(text)
        assert json.loads(result) == {"a": [1, 2], "b": {"c": 3}}


# =============================================================================
# Retry Logic Tests (mock Claude API)
# =============================================================================


def _make_mock_response(text_content: str):
    """Create a mock Anthropic response with given text content."""
    mock_block = MagicMock()
    mock_block.text = text_content

    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_response.usage = MagicMock()
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50
    mock_response.usage.cache_read_input_tokens = 0

    return mock_response


def _make_empty_response():
    """Create a mock Anthropic response with no text blocks."""
    mock_block = MagicMock(spec=[])  # no text attribute
    del mock_block.text  # ensure hasattr fails

    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_response.usage = MagicMock()

    return mock_response


class TestCallWithSchemaRetry:
    """Tests for ClaudeService._call_with_schema_retry()."""

    def _make_service(self, mock_create):
        """Create a ClaudeService with a mocked client."""
        with patch("app.services.ai_service.settings") as mock_settings:
            mock_settings.anthropic_api_key = "test-key"
            mock_settings.anthropic_timeout = 30
            mock_settings.anthropic_connect_timeout = 10
            mock_settings.haiku_model = "test-haiku"
            mock_settings.sonnet_model = "test-sonnet"

            with patch("app.services.ai_service.Anthropic") as MockAnthropic:
                mock_client = MagicMock()
                mock_client.messages.create = mock_create
                MockAnthropic.return_value = mock_client

                from app.services.ai_service import ClaudeService

                service = ClaudeService()
                return service

    def test_first_attempt_succeeds(self):
        """Valid response on first try - no retries needed."""
        valid_json = '"meal_name": "Toast", "ingredients": [{"name": "bread", "state": "cooked", "quantity": "1 slice", "confidence": 0.9}]}'
        mock_create = MagicMock(return_value=_make_mock_response(valid_json))
        service = self._make_service(mock_create)

        messages = [{"role": "user", "content": "Analyze this meal."}]
        validated, raw_text, response = service._call_with_schema_retry(
            messages=messages,
            schema_class=MealAnalysisSchema,
            request_params={"model": "test", "max_tokens": 100},
        )

        assert validated["meal_name"] == "Toast"
        assert len(validated["ingredients"]) == 1
        assert mock_create.call_count == 1
        # Messages should NOT be mutated on success
        assert len(messages) == 1

    def test_retry_on_bad_json_then_succeeds(self):
        """First attempt returns invalid JSON, second succeeds."""
        bad_response = _make_mock_response("not json at all")
        good_json = '"meal_name": "Toast", "ingredients": [{"name": "bread", "state": "cooked", "confidence": 0.9}]}'
        good_response = _make_mock_response(good_json)

        mock_create = MagicMock(side_effect=[bad_response, good_response])
        service = self._make_service(mock_create)

        messages = [{"role": "user", "content": "Analyze this meal."}]
        validated, raw_text, response = service._call_with_schema_retry(
            messages=messages,
            schema_class=MealAnalysisSchema,
            request_params={"model": "test", "max_tokens": 100},
        )

        assert validated["meal_name"] == "Toast"
        assert mock_create.call_count == 2
        # Messages should have grown: original + failed attempt + error feedback
        assert len(messages) == 3

    def test_retry_on_schema_error_then_succeeds(self):
        """Valid JSON but wrong schema, then correct on retry."""
        # Missing required field 'ingredients'
        bad_schema = '"meal_name": "Toast"}'
        bad_response = _make_mock_response(bad_schema)

        good_json = '"meal_name": "Toast", "ingredients": [{"name": "bread", "state": "cooked", "confidence": 0.9}]}'
        good_response = _make_mock_response(good_json)

        mock_create = MagicMock(side_effect=[bad_response, good_response])
        service = self._make_service(mock_create)

        messages = [{"role": "user", "content": "Analyze this meal."}]
        validated, raw_text, response = service._call_with_schema_retry(
            messages=messages,
            schema_class=MealAnalysisSchema,
            request_params={"model": "test", "max_tokens": 100},
        )

        assert validated["meal_name"] == "Toast"
        assert mock_create.call_count == 2

    def test_all_attempts_fail(self):
        """All 3 attempts fail - ValueError raised."""
        bad_response = _make_mock_response("not valid json {{{")

        mock_create = MagicMock(return_value=bad_response)
        service = self._make_service(mock_create)

        messages = [{"role": "user", "content": "Analyze this meal."}]
        with pytest.raises(
            ValueError, match="failed schema validation after 3 attempts"
        ):
            service._call_with_schema_retry(
                messages=messages,
                schema_class=MealAnalysisSchema,
                request_params={"model": "test", "max_tokens": 100},
            )

        assert mock_create.call_count == 3

    def test_empty_response_retries(self):
        """Empty response triggers retry."""
        empty_response = _make_empty_response()
        good_json = '"meal_name": "Toast", "ingredients": []}'
        good_response = _make_mock_response(good_json)

        mock_create = MagicMock(side_effect=[empty_response, good_response])
        service = self._make_service(mock_create)

        messages = [{"role": "user", "content": "Analyze this meal."}]
        validated, raw_text, response = service._call_with_schema_retry(
            messages=messages,
            schema_class=MealAnalysisSchema,
            request_params={"model": "test", "max_tokens": 100},
        )

        assert validated["meal_name"] == "Toast"
        assert mock_create.call_count == 2

    def test_all_empty_responses_raise(self):
        """All empty responses raise ValueError."""
        empty_response = _make_empty_response()
        mock_create = MagicMock(return_value=empty_response)
        service = self._make_service(mock_create)

        messages = [{"role": "user", "content": "Analyze this meal."}]
        with pytest.raises(ValueError, match="No text content"):
            service._call_with_schema_retry(
                messages=messages,
                schema_class=MealAnalysisSchema,
                request_params={"model": "test", "max_tokens": 100},
            )

    def test_image_context_preserved_on_retry(self):
        """Image content in messages is preserved across retries."""
        bad_response = _make_mock_response("not json")
        good_json = '"meal_name": "Salad", "ingredients": [{"name": "lettuce", "state": "raw", "confidence": 0.8}]}'
        good_response = _make_mock_response(good_json)

        mock_create = MagicMock(side_effect=[bad_response, good_response])
        service = self._make_service(mock_create)

        # Messages with image content
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": "base64data...",
                        },
                    },
                    {"type": "text", "text": "Analyze this meal."},
                ],
            }
        ]

        validated, raw_text, response = service._call_with_schema_retry(
            messages=messages,
            schema_class=MealAnalysisSchema,
            request_params={"model": "test", "max_tokens": 100},
        )

        # Image should still be in the first message
        assert messages[0]["role"] == "user"
        assert isinstance(messages[0]["content"], list)
        assert messages[0]["content"][0]["type"] == "image"

        # On the retry call, the messages should include the image
        second_call_messages = mock_create.call_args_list[1][1]["messages"]
        assert second_call_messages[0]["content"][0]["type"] == "image"

    def test_prefill_included_in_call(self):
        """Prefill '{' is added to each API call."""
        good_json = '"meal_name": "Toast", "ingredients": []}'
        good_response = _make_mock_response(good_json)
        mock_create = MagicMock(return_value=good_response)
        service = self._make_service(mock_create)

        messages = [{"role": "user", "content": "Analyze."}]
        service._call_with_schema_retry(
            messages=messages,
            schema_class=MealAnalysisSchema,
            request_params={"model": "test", "max_tokens": 100},
            prefill="{",
        )

        # Check that the messages passed to create include the prefill
        call_messages = mock_create.call_args[1]["messages"]
        assert call_messages[-1] == {"role": "assistant", "content": "{"}

    def test_no_prefill(self):
        """When prefill=None, no assistant message added."""
        # Full JSON response (no prefill means we need the opening brace)
        good_json = '{"is_continuation": true, "confidence": 0.9, "reasoning": "Same symptoms."}'
        good_response = _make_mock_response(good_json)
        mock_create = MagicMock(return_value=good_response)
        service = self._make_service(mock_create)

        messages = [{"role": "user", "content": "Analyze."}]
        validated, raw_text, response = service._call_with_schema_retry(
            messages=messages,
            schema_class=EpisodeContinuationSchema,
            request_params={"model": "test", "max_tokens": 100},
            prefill=None,
        )

        assert validated["is_continuation"] is True
        # No prefill assistant message
        call_messages = mock_create.call_args[1]["messages"]
        assert all(m["role"] == "user" for m in call_messages)

    def test_markdown_wrapped_response(self):
        """Response wrapped in markdown code blocks is handled."""
        markdown_json = '```json\n{"meal_name": "Toast", "ingredients": []}\n```'
        # With prefill "{", the full text would be "{```json..." which is wrong
        # So this test uses prefill=None
        mock_create = MagicMock(return_value=_make_mock_response(markdown_json))
        service = self._make_service(mock_create)

        messages = [{"role": "user", "content": "Analyze."}]
        validated, raw_text, response = service._call_with_schema_retry(
            messages=messages,
            schema_class=MealAnalysisSchema,
            request_params={"model": "test", "max_tokens": 100},
            prefill=None,
        )

        assert validated["meal_name"] == "Toast"

    def test_trailing_commas_fixed(self):
        """Response with trailing commas is fixed before parsing."""
        json_with_commas = (
            '"root_cause": true, "medical_reasoning": "Strong evidence.",}'
        )
        mock_create = MagicMock(return_value=_make_mock_response(json_with_commas))
        service = self._make_service(mock_create)

        messages = [{"role": "user", "content": "Classify."}]
        validated, raw_text, response = service._call_with_schema_retry(
            messages=messages,
            schema_class=RootCauseSchema,
            request_params={"model": "test", "max_tokens": 100},
        )

        assert validated["root_cause"] is True

    def test_discriminated_union_schema(self):
        """ClarifySymptomSchema (discriminated union) works with retry helper."""
        question_json = '"mode": "question", "question": "When did it start?"}'
        mock_create = MagicMock(return_value=_make_mock_response(question_json))
        service = self._make_service(mock_create)

        messages = [{"role": "user", "content": "I feel sick."}]
        validated, raw_text, response = service._call_with_schema_retry(
            messages=messages,
            schema_class=ClarifySymptomSchema,
            request_params={"model": "test", "max_tokens": 100},
        )

        assert validated["mode"] == "question"
        assert validated["question"] == "When did it start?"

    def test_custom_max_retries(self):
        """Custom max_retries=0 means only 1 attempt."""
        bad_response = _make_mock_response("not json")
        mock_create = MagicMock(return_value=bad_response)
        service = self._make_service(mock_create)

        messages = [{"role": "user", "content": "Analyze."}]
        with pytest.raises(ValueError, match="after 1 attempts"):
            service._call_with_schema_retry(
                messages=messages,
                schema_class=MealAnalysisSchema,
                request_params={"model": "test", "max_tokens": 100},
                max_retries=0,
            )

        assert mock_create.call_count == 1

    def test_error_feedback_includes_schema_error(self):
        """Retry feedback message includes the actual validation error."""
        # Valid JSON but ingredient has confidence > 1 (violates ge=0, le=1)
        bad_schema = (
            '"ingredients": [{"name": "x", "state": "raw", "confidence": 5.0}]}'
        )
        bad_response = _make_mock_response(bad_schema)
        good_json = '"meal_name": "X", "ingredients": [{"name": "x", "state": "raw", "confidence": 0.9}]}'
        good_response = _make_mock_response(good_json)

        mock_create = MagicMock(side_effect=[bad_response, good_response])
        service = self._make_service(mock_create)

        messages = [{"role": "user", "content": "Analyze."}]
        service._call_with_schema_retry(
            messages=messages,
            schema_class=MealAnalysisSchema,
            request_params={"model": "test", "max_tokens": 100},
        )

        # Check the error feedback message was added
        assert len(messages) == 3
        error_msg = messages[2]["content"]
        assert "schema error" in error_msg
        assert "confidence" in error_msg  # Should mention the invalid field

    def test_multi_block_response(self):
        """Response with multiple content blocks (web search) extracts all text."""
        # Simulate web search response with multiple text blocks
        block1 = MagicMock()
        block1.text = '"root_cause": true, '

        block2 = MagicMock()
        block2.text = '"medical_reasoning": "Evidence."}'

        # Web search result block (no text attr)
        search_block = MagicMock(spec=[])

        mock_response = MagicMock()
        mock_response.content = [search_block, block1, block2]
        mock_response.usage = MagicMock()

        mock_create = MagicMock(return_value=mock_response)
        service = self._make_service(mock_create)

        messages = [{"role": "user", "content": "Classify."}]
        validated, raw_text, response = service._call_with_schema_retry(
            messages=messages,
            schema_class=RootCauseSchema,
            request_params={"model": "test", "max_tokens": 100},
        )

        assert validated["root_cause"] is True
        assert validated["medical_reasoning"] == "Evidence."

    def test_retry_feedback_includes_schema_definition(self):
        """Retry error feedback includes the JSON Schema so the model can self-correct."""
        bad_schema = '"ingredients": [{"name": "x", "state": "raw", "confidence": 5.0}]}'
        bad_response = _make_mock_response(bad_schema)
        good_json = '"meal_name": "X", "ingredients": [{"name": "x", "state": "raw", "confidence": 0.9}]}'
        good_response = _make_mock_response(good_json)

        mock_create = MagicMock(side_effect=[bad_response, good_response])
        service = self._make_service(mock_create)

        messages = [{"role": "user", "content": "Analyze."}]
        service._call_with_schema_retry(
            messages=messages,
            schema_class=MealAnalysisSchema,
            request_params={"model": "test", "max_tokens": 100},
        )

        # The error feedback (messages[2]) should contain the JSON schema
        error_feedback = messages[2]["content"]
        assert "Required JSON Schema" in error_feedback
        assert '"properties"' in error_feedback
        assert "meal_name" in error_feedback


# =============================================================================
# Regression: stop_sequences must not appear in diagnosis request_params
# =============================================================================


class TestNoStopSequences:
    """Ensure stop_sequences are not used in any diagnosis method."""

    def _make_service(self):
        """Create a ClaudeService with a recording mock client."""
        with patch("app.services.ai_service.settings") as mock_settings:
            mock_settings.anthropic_api_key = "test-key"
            mock_settings.anthropic_timeout = 30
            mock_settings.anthropic_connect_timeout = 10
            mock_settings.haiku_model = "test-haiku"
            mock_settings.sonnet_model = "test-sonnet"

            with patch("app.services.ai_service.Anthropic") as MockAnthropic:
                mock_client = MagicMock()
                MockAnthropic.return_value = mock_client
                from app.services.ai_service import ClaudeService

                service = ClaudeService()
                return service, mock_client

    def _make_valid_response(self, schema_class):
        """Return a mock response valid for the given schema."""
        from app.services.ai_schemas import (
            RootCauseSchema,
            ResearchIngredientSchema,
            SingleIngredientDiagnosisSchema,
            DiagnosisCorrelationsSchema,
        )

        responses = {
            DiagnosisCorrelationsSchema: '{"ingredient_analyses": [], "overall_summary": "ok", "caveats": []}',
            SingleIngredientDiagnosisSchema: '{"diagnosis_summary": "s", "recommendations_summary": "r", "alternative_meals": [], "citations": []}',
            RootCauseSchema: '{"root_cause": true, "medical_reasoning": "reason"}',
            ResearchIngredientSchema: '{"medical_assessment": "ok", "known_trigger_categories": [], "risk_level": "low_risk", "citations": []}',
        }
        # Return prefill-compatible (without opening brace since prefill adds it)
        full = responses[schema_class]
        # Strip leading { since prefill adds it
        return _make_mock_response(full[1:])

    def test_diagnose_correlations_no_stop_sequences(self):
        service, mock_client = self._make_service()
        from app.services.ai_schemas import DiagnosisCorrelationsSchema

        mock_client.messages.create.return_value = self._make_valid_response(
            DiagnosisCorrelationsSchema
        )

        import asyncio

        asyncio.get_event_loop().run_until_complete(
            service.diagnose_correlations(
                [{"ingredient_name": "milk", "state": "raw", "times_eaten": 5,
                  "total_symptom_occurrences": 3, "immediate_total": 1,
                  "delayed_total": 1, "cumulative_total": 1,
                  "associated_symptoms": []}],
                web_search_enabled=False,
            )
        )

        call_kwargs = mock_client.messages.create.call_args[1]
        assert "stop_sequences" not in call_kwargs

    def test_classify_root_cause_no_stop_sequences(self):
        service, mock_client = self._make_service()
        from app.services.ai_schemas import RootCauseSchema

        mock_client.messages.create.return_value = self._make_valid_response(
            RootCauseSchema
        )

        import asyncio

        asyncio.get_event_loop().run_until_complete(
            service.classify_root_cause(
                ingredient_data={"ingredient_name": "milk", "times_eaten": 5,
                                  "total_symptom_occurrences": 3,
                                  "confidence_level": "medium",
                                  "associated_symptoms": []},
                cooccurrence_data=[],
                medical_grounding="Known trigger.",
                web_search_enabled=False,
            )
        )

        call_kwargs = mock_client.messages.create.call_args[1]
        assert "stop_sequences" not in call_kwargs


# =============================================================================
# AlternativeMealSchema optional meal_id
# =============================================================================


class TestAlternativeMealSchemaOptionalId:
    def test_meal_id_none(self):
        data = {"meal_id": None, "name": "Oat Bowl", "reason": "No dairy"}
        result = AlternativeMealSchema.model_validate(data)
        assert result.meal_id is None

    def test_meal_id_missing(self):
        data = {"name": "Oat Bowl", "reason": "No dairy"}
        result = AlternativeMealSchema.model_validate(data)
        assert result.meal_id is None

    def test_meal_id_present(self):
        data = {"meal_id": 42, "name": "Oat Bowl", "reason": "No dairy"}
        result = AlternativeMealSchema.model_validate(data)
        assert result.meal_id == 42


# =============================================================================
# Extended _strip_markdown_json tests
# =============================================================================


class TestStripMarkdownJsonExtended:
    def test_backticks_inside_json_string_values(self):
        """JSON with backticks in string values (e.g. citations) should not break parsing."""
        text = '{"url": "https://example.com/page```test", "title": "Study"}'
        result = _strip_markdown_json(text)
        assert '"url"' in result
        parsed = json.loads(result)
        assert parsed["title"] == "Study"

    def test_explanatory_text_before_json(self):
        """Explanatory text before JSON object is stripped."""
        text = 'Here is the analysis result:\n{"key": "value"}'
        result = _strip_markdown_json(text)
        assert result == '{"key": "value"}'

    def test_explanatory_text_after_json(self):
        """Explanatory text after JSON object is stripped."""
        text = '{"key": "value"}\n\nI hope this helps!'
        result = _strip_markdown_json(text)
        assert result == '{"key": "value"}'

    def test_json_array_extraction(self):
        """JSON array is extracted from surrounding text."""
        text = 'Results:\n[{"a": 1}, {"a": 2}]\nDone.'
        result = _strip_markdown_json(text)
        assert result == '[{"a": 1}, {"a": 2}]'

    def test_nested_json_preserved(self):
        """Nested JSON objects are preserved."""
        text = '{"outer": {"inner": "value"}}'
        result = _strip_markdown_json(text)
        parsed = json.loads(result)
        assert parsed["outer"]["inner"] == "value"

    def test_plain_json_unchanged(self):
        """Plain JSON without any wrapping passes through."""
        text = '{"key": "value"}'
        assert _strip_markdown_json(text) == text
