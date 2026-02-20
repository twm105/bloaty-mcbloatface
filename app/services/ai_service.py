"""
Claude AI integration service for meal analysis, symptom clarification, and pattern analysis.

This service provides three core AI capabilities:
1. Meal image analysis with ingredient detection (Haiku)
2. Conversational symptom clarification (Sonnet)
3. Pattern analysis with prompt caching (Sonnet)
"""

import json
import re
import base64
import asyncio
import random
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime
from functools import wraps

from anthropic import Anthropic
import anthropic
import httpx
from pydantic import BaseModel, TypeAdapter, ValidationError

from app.config import settings
from app.services.ai_schemas import (
    MealAnalysisSchema,
    ClarifySymptomSchema,
    EpisodeContinuationSchema,
    DiagnosisCorrelationsSchema,
    SingleIngredientDiagnosisSchema,
    RootCauseSchema,
    ResearchIngredientSchema,
    AdaptToPlainEnglishSchema,
)
from app.services.prompts import (
    MEAL_VALIDATION_SYSTEM_PROMPT,
    MEAL_ANALYSIS_SYSTEM_PROMPT,
    SYMPTOM_CLARIFICATION_SYSTEM_PROMPT,
    SYMPTOM_ELABORATION_SYSTEM_PROMPT,
    EPISODE_CONTINUATION_SYSTEM_PROMPT,
    DIAGNOSIS_SINGLE_INGREDIENT_PROMPT,
    ROOT_CAUSE_CLASSIFICATION_PROMPT,
    RESEARCH_INGREDIENT_PROMPT,
    ADAPT_TO_PLAIN_ENGLISH_PROMPT,
    build_cached_analysis_context,
)


logger = logging.getLogger(__name__)


def _strip_markdown_json(text: str) -> str:
    """Strip markdown code block wrappers from JSON text."""
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    return text


def _fix_trailing_commas(text: str) -> str:
    """Fix trailing commas in JSON (common LLM error)."""
    text = re.sub(r",\s*}", "}", text)
    text = re.sub(r",\s*]", "]", text)
    return text


def retry_on_connection_error(max_attempts=3, base_delay=1.0):
    """
    Retry decorator for API calls that may fail due to transient network issues.

    Args:
        max_attempts: Maximum retry attempts (default 3)
        base_delay: Base delay in seconds for exponential backoff (default 1.0)
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except anthropic.APIConnectionError as e:
                    last_exception = e

                    if attempt < max_attempts - 1:
                        # Exponential backoff with jitter
                        delay = base_delay * (2**attempt)
                        jitter = (
                            delay * 0.1 * (2 * random.random() - 1)
                        )  # ±10% random variance
                        sleep_time = delay + jitter

                        logger.warning(
                            "Connection error on attempt %d/%d, retrying in %.1fs...",
                            attempt + 1,
                            max_attempts,
                            sleep_time,
                        )
                        await asyncio.sleep(sleep_time)
                    else:
                        logger.error("All %d attempts failed", max_attempts)

            # All retries exhausted, raise the last exception
            raise ServiceUnavailableError(
                "AI service temporarily unavailable after retries"
            ) from last_exception

        return wrapper

    return decorator


class ClaudeService:
    """Centralized Claude API integration for all AI features."""

    def __init__(self):
        # Configure client with extended timeouts for web search operations
        timeout = httpx.Timeout(
            timeout=settings.anthropic_timeout,  # 180 seconds total
            connect=settings.anthropic_connect_timeout,  # 10 seconds to connect
        )
        self.client = Anthropic(api_key=settings.anthropic_api_key, timeout=timeout)
        self.haiku_model = settings.haiku_model
        self.sonnet_model = settings.sonnet_model

    # =========================================================================
    # SCHEMA VALIDATION + CONVERSATIONAL RETRY
    # =========================================================================

    def _call_with_schema_retry(
        self,
        messages: list[dict],
        schema_class: type[BaseModel],
        request_params: dict,
        max_retries: int = 2,
        prefill: str | None = "{",
    ) -> tuple[dict, str, object]:
        """
        Call Claude API with JSON schema validation and conversational retry.

        On schema failure: appends the bad response + error feedback to messages,
        re-calls with full conversation context so the LLM can self-correct.

        Args:
            messages: The messages list (will be mutated on retry)
            schema_class: Pydantic model class to validate against
            request_params: Dict of params for client.messages.create
                            (model, max_tokens, system, etc.)
                            NOTE: do NOT include 'messages' - they're passed separately
            max_retries: Number of retry attempts after initial call (default 2, so 3 total)
            prefill: Assistant prefill string, or None for no prefill

        Returns:
            (validated_dict, raw_response_text, response_object) tuple

        Raises:
            ValueError: If all attempts fail schema validation
        """
        response = None

        for attempt in range(1 + max_retries):
            # Build messages with prefill
            call_messages = list(messages)  # copy
            if prefill:
                call_messages.append({"role": "assistant", "content": prefill})

            # Make API call
            response = self.client.messages.create(
                messages=call_messages,
                **request_params,
            )

            # Extract text from response (handle multi-block web search responses)
            response_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    response_text += block.text

            if not response_text:
                if attempt < max_retries:
                    messages.append(
                        {"role": "assistant", "content": "(empty response)"}
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": "Your response contained no text. Please respond with valid JSON.",
                        }
                    )
                    continue
                raise ValueError("No text content in AI response after retries")

            # Reconstruct JSON (handle prefill)
            raw_text = response_text.strip()
            json_str = (prefill or "") + raw_text if prefill else raw_text

            # Handle markdown code blocks and trailing commas
            json_str = _strip_markdown_json(json_str)
            json_str = _fix_trailing_commas(json_str)

            # Try parse + validate
            try:
                parsed = json.loads(json_str)
                adapter = TypeAdapter(schema_class)
                validated = adapter.validate_python(parsed)
                return validated.model_dump(), raw_text, response
            except (json.JSONDecodeError, ValidationError) as e:
                error_msg = str(e)
                logger.warning(
                    "AI response schema validation failed (attempt %d/%d) for %s: %s",
                    attempt + 1,
                    1 + max_retries,
                    schema_class.__name__,
                    error_msg,
                )

                if attempt < max_retries:
                    # Append the failed attempt + error to conversation
                    messages.append(
                        {
                            "role": "assistant",
                            "content": (prefill or "") + raw_text,
                        }
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"Your response had a schema error:\n{error_msg}\n\n"
                                f"Please fix and return valid JSON matching the required schema."
                            ),
                        }
                    )
                    continue

                raise ValueError(
                    f"AI response failed schema validation after {1 + max_retries} attempts: {error_msg}"
                )

        # Should not reach here, but just in case
        raise ValueError("AI response failed schema validation")

    # =========================================================================
    # MEAL IMAGE ANALYSIS (Task #5)
    # =========================================================================

    async def validate_meal_image(self, image_path: str) -> bool:
        """
        Quick safety check: Is this image actually a meal/food?

        Uses Haiku with simple yes/no prompt to reject:
        - Non-food images (selfies, documents, random photos)
        - Inappropriate content
        - Low-quality/corrupted images

        Args:
            image_path: Path to uploaded image file

        Returns:
            True if meal detected, False otherwise

        Cost: ~$0.0005 per validation
        """
        try:
            # Read and encode image
            image_data = self._load_image_base64(image_path)
            media_type = self._get_media_type(image_path)

            # Call Claude with validation prompt
            response = self.client.messages.create(
                model=self.haiku_model,
                max_tokens=10,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_data,
                                },
                            },
                            {
                                "type": "text",
                                "text": "Is this a photo of food or a meal? Answer only YES or NO.",
                            },
                        ],
                    }
                ],
                system=MEAL_VALIDATION_SYSTEM_PROMPT,
            )

            answer = response.content[0].text.strip().upper()
            return answer == "YES"

        except anthropic.APIConnectionError as e:
            raise ServiceUnavailableError("AI service temporarily unavailable") from e
        except anthropic.RateLimitError as e:
            raise RateLimitError(
                "Too many requests, please try again in 1 minute"
            ) from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                raise ServiceUnavailableError("AI service error") from e
            raise ValueError(f"Request error: {e.message}") from e
        except Exception as e:
            raise ValueError(f"Image validation failed: {str(e)}") from e

    async def analyze_meal_image(
        self, image_path: str, user_notes: Optional[str] = None
    ) -> dict:
        """
        Analyze meal image with Haiku, return structured ingredients.

        Args:
            image_path: Path to uploaded meal image
            user_notes: Optional user-provided context about the meal

        Returns:
            {
                "meal_name": "Grilled Chicken Salad",
                "ingredients": [
                    {
                        "name": "chicken breast",
                        "state": "cooked",
                        "quantity": "150g",
                        "confidence": 0.92
                    }
                ],
                "raw_response": "...",
                "model": "claude-sonnet-4-5-20250929"
            }

        Cost: ~$0.0024 per meal (~2,350 tokens)

        Raises:
            ServiceUnavailableError: AI service temporarily down
            RateLimitError: Too many requests
            ValueError: Invalid response or request error
        """
        try:
            # Read and encode image
            image_data = self._load_image_base64(image_path)
            media_type = self._get_media_type(image_path)

            # Build user message with optional notes
            user_message = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_data,
                    },
                },
                {
                    "type": "text",
                    "text": "Analyze this meal and identify all visible ingredients.",
                },
            ]

            if user_notes:
                user_message.append(
                    {"type": "text", "text": f"User notes: {user_notes}"}
                )

            messages = [{"role": "user", "content": user_message}]

            validated, raw_text, _response = self._call_with_schema_retry(
                messages=messages,
                schema_class=MealAnalysisSchema,
                request_params={
                    "model": self.haiku_model,
                    "max_tokens": 1024,
                    "system": MEAL_ANALYSIS_SYSTEM_PROMPT,
                },
            )

            return {
                "meal_name": validated["meal_name"],
                "ingredients": validated["ingredients"],
                "raw_response": raw_text,
                "model": self.haiku_model,
            }

        except anthropic.APIConnectionError as e:
            raise ServiceUnavailableError("AI service temporarily unavailable") from e
        except anthropic.RateLimitError as e:
            raise RateLimitError(
                "Too many requests, please try again in 1 minute"
            ) from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                raise ServiceUnavailableError("AI service error") from e
            raise ValueError(f"Request error: {e.message}") from e

    # =========================================================================
    # SYMPTOM CLARIFICATION (Task #6)
    # =========================================================================

    async def clarify_symptom(
        self, raw_description: str, clarification_history: list = None
    ) -> dict:
        """
        Multi-turn symptom clarification with Sonnet (max 3 questions).

        Args:
            raw_description: User's initial symptom description
            clarification_history: List of {question: str, answer: str, skipped: bool}

        Returns:
            If mode="question":
            {
                "mode": "question",
                "question": "When did you first notice the symptoms?"
            }

            If mode="complete":
            {
                "mode": "complete",
                "structured": {
                    "type": "bloating",
                    "severity": 6,
                    "notes": "Bloating after dinner, lasted 2 hours, severity 6/10"
                }
            }

        Cost: ~$0.0126 per symptom (~4,200 tokens over 3 turns)

        Raises:
            ServiceUnavailableError: AI service temporarily down
            RateLimitError: Too many requests
            ValueError: Invalid response or request error
        """
        if clarification_history is None:
            clarification_history = []

        try:
            # Build conversation messages
            messages = [
                {
                    "role": "user",
                    "content": f"My symptom description: {raw_description}",
                }
            ]

            # Add clarification Q&A to messages
            for item in clarification_history:
                if not item.get("skipped", False):
                    messages.append(
                        {
                            "role": "assistant",
                            "content": json.dumps(
                                {"mode": "question", "question": item["question"]}
                            ),
                        }
                    )
                    messages.append({"role": "user", "content": item["answer"]})
                else:
                    # User skipped this question
                    messages.append(
                        {
                            "role": "assistant",
                            "content": json.dumps(
                                {"mode": "question", "question": item["question"]}
                            ),
                        }
                    )
                    messages.append(
                        {"role": "user", "content": "I'd prefer to skip this question."}
                    )

            # Add instruction to proceed
            messages.append(
                {
                    "role": "user",
                    "content": f"Questions asked so far: {len(clarification_history)}. Please proceed.",
                }
            )

            validated, _raw_text, _response = self._call_with_schema_retry(
                messages=messages,
                schema_class=ClarifySymptomSchema,
                request_params={
                    "model": self.sonnet_model,
                    "max_tokens": 512,
                    "system": SYMPTOM_CLARIFICATION_SYSTEM_PROMPT,
                },
            )

            return validated

        except anthropic.APIConnectionError as e:
            raise ServiceUnavailableError("AI service temporarily unavailable") from e
        except anthropic.RateLimitError as e:
            raise RateLimitError(
                "Too many requests, please try again in 1 minute"
            ) from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                raise ServiceUnavailableError("AI service error") from e
            raise ValueError(f"Request error: {e.message}") from e

    # =========================================================================
    # SYMPTOM ELABORATION & EPISODE DETECTION
    # =========================================================================

    async def elaborate_symptom_tags_streaming(
        self,
        tags: list,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        user_notes: Optional[str] = None,
    ):
        """
        Stream AI-generated medical note from symptom tags (async generator).

        Args:
            tags: List of {"name": str, "severity": int}
            start_time: When symptoms began
            end_time: When symptoms ended (if applicable)
            user_notes: Optional user context

        Yields:
            Text chunks as they arrive from Claude API

        Cost: ~$0.003 per elaboration (~1000 tokens)

        Raises:
            ServiceUnavailableError: AI service temporarily down
            RateLimitError: Too many requests
            ValueError: Invalid response or request error
        """
        try:
            # Build context string (same as non-streaming)
            context_parts = [f"Tags: {json.dumps(tags)}"]

            if start_time:
                context_parts.append(
                    f"Start time: {start_time.strftime('%Y-%m-%d %H:%M')}"
                )

            if end_time:
                duration = end_time - start_time
                hours = duration.total_seconds() / 3600
                context_parts.append(
                    f"End time: {end_time.strftime('%Y-%m-%d %H:%M')} (duration: {hours:.1f} hours)"
                )

            if user_notes:
                context_parts.append(f"User notes: {user_notes}")

            context = "\n".join(context_parts)

            # Use streaming API
            with self.client.messages.stream(
                model=self.sonnet_model,
                max_tokens=512,
                messages=[
                    {
                        "role": "user",
                        "content": f"Generate a medical note paragraph from this symptom data:\n\n{context}",
                    }
                ],
                system=SYMPTOM_ELABORATION_SYSTEM_PROMPT,
            ) as stream:
                for text in stream.text_stream:
                    yield text

        except anthropic.APIConnectionError as e:
            raise ServiceUnavailableError("AI service temporarily unavailable") from e
        except anthropic.RateLimitError as e:
            raise RateLimitError(
                "Too many requests, please try again in 1 minute"
            ) from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                raise ServiceUnavailableError("AI service error") from e
            raise ValueError(f"Request error: {e.message}") from e

    async def elaborate_symptom_tags(
        self,
        tags: list,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        user_notes: Optional[str] = None,
    ) -> dict:
        """
        Generate medical-note paragraph from symptom tags.

        Args:
            tags: List of {"name": str, "severity": int}
            start_time: When symptoms began
            end_time: When symptoms ended (if applicable)
            user_notes: Optional user context

        Returns:
            {
                "elaboration": "Patient experienced severe bloating...",
                "raw_response": "...",
                "model": "claude-sonnet-4-5-20250929"
            }

        Cost: ~$0.003 per elaboration (~1000 tokens)

        Raises:
            ServiceUnavailableError: AI service temporarily down
            RateLimitError: Too many requests
            ValueError: Invalid response or request error
        """
        try:
            # Build context string
            context_parts = [f"Tags: {json.dumps(tags)}"]

            if start_time:
                context_parts.append(
                    f"Start time: {start_time.strftime('%Y-%m-%d %H:%M')}"
                )

            if end_time:
                duration = end_time - start_time
                hours = duration.total_seconds() / 3600
                context_parts.append(
                    f"End time: {end_time.strftime('%Y-%m-%d %H:%M')} (duration: {hours:.1f} hours)"
                )

            if user_notes:
                context_parts.append(f"User notes: {user_notes}")

            context = "\n".join(context_parts)

            # Call Claude
            response = self.client.messages.create(
                model=self.sonnet_model,
                max_tokens=512,
                messages=[
                    {
                        "role": "user",
                        "content": f"Generate a medical note paragraph from this symptom data:\n\n{context}",
                    }
                ],
                system=SYMPTOM_ELABORATION_SYSTEM_PROMPT,
            )

            elaboration = response.content[0].text.strip()

            return {
                "elaboration": elaboration,
                "raw_response": elaboration,
                "model": self.sonnet_model,
            }

        except anthropic.APIConnectionError as e:
            raise ServiceUnavailableError("AI service temporarily unavailable") from e
        except anthropic.RateLimitError as e:
            raise RateLimitError(
                "Too many requests, please try again in 1 minute"
            ) from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                raise ServiceUnavailableError("AI service error") from e
            raise ValueError(f"Request error: {e.message}") from e

    async def detect_ongoing_symptom(
        self, previous_symptom: dict, current_symptom: dict
    ) -> dict:
        """
        Determine if current symptom is ongoing from previous occurrence.

        Args:
            previous_symptom: {name, severity, start_time, end_time}
            current_symptom: {name, severity, time}

        Returns:
            {
                "is_ongoing": bool,
                "confidence": float (0-1),
                "reasoning": str
            }
        """
        try:
            # Build analysis context
            analysis_data = {
                "previous_symptom": {
                    "name": previous_symptom.get("name"),
                    "severity": previous_symptom.get("severity"),
                    "start_time": previous_symptom.get("start_time").isoformat()
                    if isinstance(previous_symptom.get("start_time"), datetime)
                    else previous_symptom.get("start_time"),
                    "end_time": previous_symptom.get("end_time").isoformat()
                    if previous_symptom.get("end_time")
                    else None,
                },
                "current_symptom": {
                    "name": current_symptom.get("name"),
                    "severity": current_symptom.get("severity"),
                    "time": current_symptom.get("time").isoformat()
                    if isinstance(current_symptom.get("time"), datetime)
                    else current_symptom.get("time"),
                },
            }

            messages = [
                {
                    "role": "user",
                    "content": f"Analyze if this symptom is ongoing:\n\n{json.dumps(analysis_data, indent=2)}",
                }
            ]

            validated, _raw_text, _response = self._call_with_schema_retry(
                messages=messages,
                schema_class=EpisodeContinuationSchema,
                request_params={
                    "model": self.sonnet_model,
                    "max_tokens": 512,
                    "system": EPISODE_CONTINUATION_SYSTEM_PROMPT,
                },
            )

            return {
                "is_ongoing": validated[
                    "is_continuation"
                ],  # Remap field name for caller
                "confidence": validated["confidence"],
                "reasoning": validated["reasoning"],
            }

        except (
            anthropic.APIConnectionError,
            anthropic.RateLimitError,
            anthropic.APIStatusError,
        ):
            raise
        except Exception as e:
            raise ValueError(f"AI ongoing detection failed: {str(e)}")

    async def detect_episode_continuation(
        self, current_tags: list, current_time: datetime, previous_symptom: dict
    ) -> dict:
        """
        Determine if current symptoms continue a previous episode.

        Args:
            current_tags: List of {"name": str, "severity": int}
            current_time: When current symptoms began
            previous_symptom: Dict with keys: tags, start_time, end_time, notes

        Returns:
            {
                "is_continuation": bool,
                "confidence": float (0-1),
                "reasoning": str
            }

        Cost: ~$0.002 per check (~700 tokens)

        Raises:
            ServiceUnavailableError: AI service temporarily down
            RateLimitError: Too many requests
            ValueError: Invalid response or request error
        """
        try:
            # Build analysis context
            analysis_data = {
                "current_tags": current_tags,
                "current_time": current_time.isoformat(),
                "previous_symptom": {
                    "tags": previous_symptom.get("tags"),
                    "start_time": previous_symptom.get("start_time").isoformat()
                    if previous_symptom.get("start_time")
                    else None,
                    "end_time": previous_symptom.get("end_time").isoformat()
                    if previous_symptom.get("end_time")
                    else None,
                    "notes": previous_symptom.get("notes"),
                },
            }

            messages = [
                {
                    "role": "user",
                    "content": f"Analyze if these symptoms are a continuation:\n\n{json.dumps(analysis_data, indent=2)}",
                }
            ]

            validated, _raw_text, _response = self._call_with_schema_retry(
                messages=messages,
                schema_class=EpisodeContinuationSchema,
                request_params={
                    "model": self.sonnet_model,
                    "max_tokens": 512,
                    "system": EPISODE_CONTINUATION_SYSTEM_PROMPT,
                },
            )

            return {
                "is_continuation": validated["is_continuation"],
                "confidence": validated["confidence"],
                "reasoning": validated["reasoning"],
            }

        except anthropic.APIConnectionError as e:
            raise ServiceUnavailableError("AI service temporarily unavailable") from e
        except anthropic.RateLimitError as e:
            raise RateLimitError(
                "Too many requests, please try again in 1 minute"
            ) from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                raise ServiceUnavailableError("AI service error") from e
            raise ValueError(f"Request error: {e.message}") from e

    # =========================================================================
    # PATTERN ANALYSIS (Task #8)
    # =========================================================================

    async def analyze_patterns(
        self,
        meals_data: str,
        symptoms_data: str,
        analysis_question: str = "Identify ingredients that may be correlated with symptoms.",
    ) -> dict:
        """
        Analyze meal-symptom correlations with Sonnet + prompt caching.

        Uses prompt caching for large datasets to save 90% on costs.

        Args:
            meals_data: Formatted string of meal data with timestamps and ingredients
            symptoms_data: Formatted string of symptom data with timestamps and types
            analysis_question: Specific question or focus for the analysis

        Returns:
            {
                "analysis": "Markdown-formatted analysis",
                "model": "claude-3-5-sonnet-20241022",
                "cache_hit": true|false,
                "input_tokens": int,
                "cached_tokens": int
            }

        Cost (first analysis): ~$0.0508 (16,100 tokens)
        Cost (cached): ~$0.0053 (90% savings)

        Raises:
            ServiceUnavailableError: AI service temporarily down
            RateLimitError: Too many requests
            ValueError: Invalid response or request error
        """
        try:
            # Build cached system context
            cached_context = build_cached_analysis_context(meals_data, symptoms_data)

            # Call Claude with prompt caching
            response = self.client.messages.create(
                model=self.sonnet_model,
                max_tokens=2048,
                system=cached_context,
                messages=[{"role": "user", "content": analysis_question}],
            )

            analysis = response.content[0].text

            # Extract token usage for cost tracking
            usage = response.usage
            cache_hit = (
                hasattr(usage, "cache_read_input_tokens")
                and usage.cache_read_input_tokens > 0
            )

            return {
                "analysis": analysis,
                "model": self.sonnet_model,
                "cache_hit": cache_hit,
                "input_tokens": usage.input_tokens,
                "cached_tokens": getattr(usage, "cache_read_input_tokens", 0),
            }

        except anthropic.APIConnectionError as e:
            raise ServiceUnavailableError("AI service temporarily unavailable") from e
        except anthropic.RateLimitError as e:
            raise RateLimitError(
                "Too many requests, please try again in 1 minute"
            ) from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                raise ServiceUnavailableError("AI service error") from e
            raise ValueError(f"Request error: {e.message}") from e

    # =========================================================================
    # DIAGNOSIS - INGREDIENT-SYMPTOM CORRELATION ANALYSIS
    # =========================================================================

    @retry_on_connection_error(max_attempts=3, base_delay=2.0)
    async def diagnose_correlations(
        self, correlation_data: list[dict], web_search_enabled: bool = True
    ) -> dict:
        """
        Analyze ingredient-symptom correlations with medical grounding via web search.

        Uses Sonnet model with web search to:
        1. Assess statistical correlation strength
        2. Research medical literature for known associations
        3. Provide scientific context and citations
        4. Interpret findings in plain language
        5. Suggest next steps

        Args:
            correlation_data: List of dicts with ingredient-symptom correlation stats
            web_search_enabled: Whether to enable web search for medical research

        Returns:
            Dict with structure:
            {
                "ingredient_analyses": [...],
                "overall_summary": str,
                "caveats": [str],
                "usage_stats": {
                    "input_tokens": int,
                    "cached_tokens": int,
                    "cache_hit": bool
                }
            }

        Raises:
            ServiceUnavailableError: AI service unavailable
            RateLimitError: Too many requests
            ValueError: Invalid response format

        Cost: ~$0.15-0.30 first run, ~$0.02-0.05 cached runs (90% savings)
        """
        try:
            # Format correlation data for AI analysis
            formatted_data = self._format_correlation_data(correlation_data)

            # Build request - import DIAGNOSIS_SYSTEM_PROMPT from prompts
            from app.services.prompts import DIAGNOSIS_SYSTEM_PROMPT

            # Validate request size before sending
            self._validate_request_size(formatted_data, DIAGNOSIS_SYSTEM_PROMPT)

            # Prepare messages (prefill handled by _call_with_schema_retry)
            messages = [
                {
                    "role": "user",
                    "content": f"""Analyze the following ingredient-symptom correlation data and provide medical context:

{formatted_data}

Remember to:
1. Research medical literature for known associations
2. Provide citations from reputable sources (NIH, PubMed, medical journals, RD sites)
3. Use qualified language (correlation, not causation)
4. Include plain-language interpretation
5. Suggest next steps including professional consultation""",
                },
            ]

            # Build request parameters (without messages - passed separately)
            request_params = {
                "model": self.sonnet_model,
                "max_tokens": 8192,
                "stop_sequences": ["\n```", "```"],
                "system": [
                    {
                        "type": "text",
                        "text": DIAGNOSIS_SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            }

            # Add web search tool if enabled
            if web_search_enabled:
                request_params["tools"] = [
                    {"type": "web_search_20250305", "name": "web_search"}
                ]

            validated, _raw_text, response = self._call_with_schema_retry(
                messages=messages,
                schema_class=DiagnosisCorrelationsSchema,
                request_params=request_params,
            )

            # Add usage stats
            usage = response.usage
            validated["usage_stats"] = {
                "input_tokens": usage.input_tokens,
                "cached_tokens": getattr(usage, "cache_read_input_tokens", 0),
                "cache_hit": getattr(usage, "cache_read_input_tokens", 0) > 0,
            }

            return validated

        except anthropic.APIConnectionError as e:
            raise ServiceUnavailableError("AI service temporarily unavailable") from e
        except anthropic.RateLimitError as e:
            raise RateLimitError(
                "Too many requests, please try again in 1 minute"
            ) from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                raise ServiceUnavailableError("AI service error") from e
            raise ValueError(f"Request error: {e.message}") from e

    @retry_on_connection_error(max_attempts=3, base_delay=2.0)
    async def diagnose_single_ingredient(
        self,
        ingredient_data: dict,
        user_meal_history: list,
        web_search_enabled: bool = True,
    ) -> dict:
        """
        Analyze a single ingredient for symptom correlations with medical grounding.

        This method is used by the async worker to process ingredients in parallel.
        Returns structured output suitable for per-ingredient result cards.

        Args:
            ingredient_data: Dict with ingredient stats and correlation data
            user_meal_history: List of user's recent meals for alternative suggestions
            web_search_enabled: Whether to enable web search for medical research

        Returns:
            Dict with structure:
            {
                "diagnosis_summary": str (3 sentences max),
                "recommendations_summary": str (3 sentences max),
                "processing_suggestions": {"cooked_vs_raw": str, "alternatives": []},
                "alternative_meals": [{"meal_id": int, "name": str, "reason": str}],
                "citations": [{"url": str, "title": str, "source_type": str, "snippet": str}],
                "usage_stats": {"input_tokens": int, "output_tokens": int, "cached_tokens": int}
            }

        Raises:
            ServiceUnavailableError: AI service unavailable
            RateLimitError: Too many requests
            ValueError: Invalid response format
        """
        try:
            # Format ingredient data for the prompt
            formatted_ingredient = self._format_single_ingredient_data(ingredient_data)

            # Format meal history for context
            meal_history_str = self._format_meal_history(user_meal_history)

            # Build user message
            user_message = f"""Analyze this ingredient for potential symptom correlations:

{formatted_ingredient}

USER'S RECENT MEALS (for alternative suggestions):
{meal_history_str}

Provide your analysis in the specified JSON format."""

            # Prepare messages (prefill handled by _call_with_schema_retry)
            messages = [{"role": "user", "content": user_message}]

            # Build request parameters (without messages)
            request_params = {
                "model": self.sonnet_model,
                "max_tokens": 2048,
                "stop_sequences": ["\n```", "```"],
                "system": [
                    {
                        "type": "text",
                        "text": DIAGNOSIS_SINGLE_INGREDIENT_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            }

            # Add web search if enabled
            if web_search_enabled:
                request_params["tools"] = [
                    {"type": "web_search_20250305", "name": "web_search"}
                ]

            validated, _raw_text, response = self._call_with_schema_retry(
                messages=messages,
                schema_class=SingleIngredientDiagnosisSchema,
                request_params=request_params,
            )

            # Add usage stats
            usage = response.usage
            validated["usage_stats"] = {
                "input_tokens": usage.input_tokens,
                "output_tokens": getattr(usage, "output_tokens", 0),
                "cached_tokens": getattr(usage, "cache_read_input_tokens", 0),
                "cache_hit": getattr(usage, "cache_read_input_tokens", 0) > 0,
            }

            return validated

        except anthropic.APIConnectionError as e:
            raise ServiceUnavailableError("AI service temporarily unavailable") from e
        except anthropic.RateLimitError as e:
            raise RateLimitError(
                "Too many requests, please try again in 1 minute"
            ) from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                raise ServiceUnavailableError("AI service error") from e
            raise ValueError(f"Request error: {e.message}") from e

    @retry_on_connection_error(max_attempts=3, base_delay=2.0)
    async def classify_root_cause(
        self,
        ingredient_data: dict,
        cooccurrence_data: list,
        medical_grounding: str,
        web_search_enabled: bool = True,
    ) -> dict:
        """
        Classify whether an ingredient is a root cause or confounder.

        This method evaluates correlation data alongside co-occurrence statistics
        and medical knowledge to determine if an ingredient is truly causing
        symptoms or merely appearing alongside actual triggers.

        Args:
            ingredient_data: Dict with ingredient stats and correlation data
            cooccurrence_data: List of co-occurrence records for this ingredient
            medical_grounding: Medical context from web search (or empty string)
            web_search_enabled: Whether to enable web search for additional context

        Returns:
            Dict with structure:
            {
                "root_cause": bool,
                "discard_justification": str or None,
                "confounded_by": str or None,
                "medical_reasoning": str,
                "usage_stats": {"input_tokens": int, "output_tokens": int}
            }

        Raises:
            ServiceUnavailableError: AI service unavailable
            RateLimitError: Too many requests
            ValueError: Invalid response format
        """
        try:
            # Format the input data for Claude
            formatted_input = self._format_root_cause_input(
                ingredient_data, cooccurrence_data, medical_grounding
            )

            # Prepare messages (prefill handled by _call_with_schema_retry)
            messages = [{"role": "user", "content": formatted_input}]

            # Build request parameters (without messages)
            request_params = {
                "model": self.sonnet_model,
                "max_tokens": 1024,
                "stop_sequences": ["\n```", "```"],
                "system": [
                    {
                        "type": "text",
                        "text": ROOT_CAUSE_CLASSIFICATION_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            }

            # Add web search if enabled and no medical grounding provided
            if web_search_enabled and not medical_grounding:
                request_params["tools"] = [
                    {"type": "web_search_20250305", "name": "web_search"}
                ]

            validated, _raw_text, response = self._call_with_schema_retry(
                messages=messages,
                schema_class=RootCauseSchema,
                request_params=request_params,
            )

            # Add usage stats
            usage = response.usage
            validated["usage_stats"] = {
                "input_tokens": usage.input_tokens,
                "output_tokens": getattr(usage, "output_tokens", 0),
                "cached_tokens": getattr(usage, "cache_read_input_tokens", 0),
            }

            return validated

        except anthropic.APIConnectionError as e:
            raise ServiceUnavailableError("AI service temporarily unavailable") from e
        except anthropic.RateLimitError as e:
            raise RateLimitError(
                "Too many requests, please try again in 1 minute"
            ) from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                raise ServiceUnavailableError("AI service error") from e
            raise ValueError(f"Request error: {e.message}") from e

    def _format_root_cause_input(
        self, ingredient_data: dict, cooccurrence_data: list, medical_grounding: str
    ) -> str:
        """Format input data for root cause classification."""
        times_eaten = ingredient_data.get("times_eaten", 0)
        symptom_count = ingredient_data.get("total_symptom_occurrences", 0)

        formatted = f"""INGREDIENT: {ingredient_data.get("ingredient_name", "Unknown")}

=== SYMPTOM PATTERN ===
- Eaten {times_eaten} times, symptoms followed {symptom_count} times
- Confidence level: {ingredient_data.get("confidence_level", "unknown")}

Symptoms reported:"""

        for symptom in ingredient_data.get("associated_symptoms", []):
            formatted += f"\n- {symptom.get('name', 'Unknown')}: {symptom.get('frequency', 0)} times"

        formatted += "\n\n=== FOODS IT APPEARS WITH ==="
        if cooccurrence_data:
            for cooc in cooccurrence_data:
                prob = cooc.get("conditional_probability", 0) * 100
                meals = cooc.get("cooccurrence_meals", 0)
                other = cooc.get("with_ingredient_name", "Unknown")

                # Convert probability to plain English
                if prob >= 90:
                    freq_desc = "almost always"
                elif prob >= 70:
                    freq_desc = "usually"
                elif prob >= 50:
                    freq_desc = "often"
                else:
                    freq_desc = "sometimes"

                formatted += (
                    f"\n- {freq_desc} eaten with {other} ({meals} meals together)"
                )
        else:
            formatted += (
                "\nThis food doesn't frequently appear with other specific foods."
            )

        formatted += "\n\n=== MEDICAL CONTEXT ==="
        if medical_grounding:
            formatted += f"\n{medical_grounding}"
        else:
            formatted += "\nPlease search for medical information about whether this food commonly causes digestive issues."

        formatted += "\n\nQUESTION: Is this food likely a real trigger, or is it just appearing alongside actual trigger foods?"

        return formatted

    @retry_on_connection_error(max_attempts=3, base_delay=2.0)
    async def research_ingredient(
        self,
        ingredient_data: dict,
        web_search_enabled: bool = True,
    ) -> dict:
        """
        Perform focused medical research on a single ingredient.

        This is a lightweight technical assessment — no plain English,
        no recommendations. Just: is this food a known digestive trigger,
        what's the mechanism, and what's the evidence?

        Args:
            ingredient_data: Dict with ingredient stats and correlation data
            web_search_enabled: Whether to enable web search for research

        Returns:
            Dict with structure:
            {
                "medical_assessment": str,
                "known_trigger_categories": list[str],
                "risk_level": str,
                "citations": list[dict],
                "usage_stats": {"input_tokens": int, "output_tokens": int}
            }
        """
        try:
            ingredient_name = ingredient_data.get("ingredient_name", "Unknown")
            times_eaten = ingredient_data.get("times_eaten", 0)
            symptom_count = ingredient_data.get("total_symptom_occurrences", 0)

            user_message = f"""Research this ingredient for digestive trigger potential:

INGREDIENT: {ingredient_name}

CORRELATION DATA:
- Eaten {times_eaten} times, symptoms followed {symptom_count} times
- Confidence level: {ingredient_data.get("confidence_level", "unknown")}

Symptoms reported:"""
            for symptom in ingredient_data.get("associated_symptoms", []):
                user_message += f"\n- {symptom.get('name', 'Unknown')}: {symptom.get('frequency', 0)} times"

            user_message += "\n\nProvide your technical medical assessment in the specified JSON format."

            messages = [{"role": "user", "content": user_message}]

            request_params = {
                "model": self.sonnet_model,
                "max_tokens": 1024,
                "stop_sequences": ["\n```", "```"],
                "system": [
                    {
                        "type": "text",
                        "text": RESEARCH_INGREDIENT_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            }

            if web_search_enabled:
                request_params["tools"] = [
                    {"type": "web_search_20250305", "name": "web_search"}
                ]

            validated, _raw_text, response = self._call_with_schema_retry(
                messages=messages,
                schema_class=ResearchIngredientSchema,
                request_params=request_params,
            )

            usage = response.usage
            validated["usage_stats"] = {
                "input_tokens": usage.input_tokens,
                "output_tokens": getattr(usage, "output_tokens", 0),
                "cached_tokens": getattr(usage, "cache_read_input_tokens", 0),
            }

            return validated

        except anthropic.APIConnectionError as e:
            raise ServiceUnavailableError("AI service temporarily unavailable") from e
        except anthropic.RateLimitError as e:
            raise RateLimitError(
                "Too many requests, please try again in 1 minute"
            ) from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                raise ServiceUnavailableError("AI service error") from e
            raise ValueError(f"Request error: {e.message}") from e

    @retry_on_connection_error(max_attempts=3, base_delay=2.0)
    async def adapt_to_plain_english(
        self,
        ingredient_data: dict,
        medical_research: dict,
        user_meal_history: list,
    ) -> dict:
        """
        Adapt technical medical research into user-facing plain English.

        Takes the output from research_ingredient() and produces the
        user-facing diagnosis summary, recommendations, and alternatives.
        No web search needed — the research was already done.

        Args:
            ingredient_data: Dict with ingredient stats and correlation data
            medical_research: Dict from research_ingredient() with
                              medical_assessment, risk_level, citations
            user_meal_history: List of user's recent meals for alternatives

        Returns:
            Dict with structure matching SingleIngredientDiagnosisSchema:
            {
                "diagnosis_summary": str,
                "recommendations_summary": str,
                "processing_suggestions": {...},
                "alternative_meals": [...],
                "citations": [...],
                "usage_stats": {...}
            }
        """
        try:
            formatted_ingredient = self._format_single_ingredient_data(ingredient_data)
            meal_history_str = self._format_meal_history(user_meal_history)

            user_message = f"""Explain this food-symptom pattern in plain English for the user.

{formatted_ingredient}

MEDICAL RESEARCH FINDINGS:
{medical_research.get("medical_assessment", "No research available.")}

Risk level: {medical_research.get("risk_level", "unknown")}
Trigger categories: {", ".join(medical_research.get("known_trigger_categories", []))}

USER'S RECENT MEALS (for alternative suggestions):
{meal_history_str}

Provide your explanation in the specified JSON format."""

            messages = [{"role": "user", "content": user_message}]

            request_params = {
                "model": self.sonnet_model,
                "max_tokens": 2048,
                "stop_sequences": ["\n```", "```"],
                "system": [
                    {
                        "type": "text",
                        "text": ADAPT_TO_PLAIN_ENGLISH_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            }

            validated, _raw_text, response = self._call_with_schema_retry(
                messages=messages,
                schema_class=AdaptToPlainEnglishSchema,
                request_params=request_params,
            )

            usage = response.usage
            validated["usage_stats"] = {
                "input_tokens": usage.input_tokens,
                "output_tokens": getattr(usage, "output_tokens", 0),
                "cached_tokens": getattr(usage, "cache_read_input_tokens", 0),
            }

            return validated

        except anthropic.APIConnectionError as e:
            raise ServiceUnavailableError("AI service temporarily unavailable") from e
        except anthropic.RateLimitError as e:
            raise RateLimitError(
                "Too many requests, please try again in 1 minute"
            ) from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                raise ServiceUnavailableError("AI service error") from e
            raise ValueError(f"Request error: {e.message}") from e

    def _format_single_ingredient_data(self, ingredient_data: dict) -> str:
        """Format single ingredient data for AI analysis."""
        times_eaten = ingredient_data.get("times_eaten", 0)
        symptom_count = ingredient_data.get("total_symptom_occurrences", 0)
        confidence_level = ingredient_data.get("confidence_level", "unknown")

        formatted = f"""INGREDIENT: {ingredient_data.get("ingredient_name", "Unknown")} ({ingredient_data.get("state", "unknown")})

PATTERN SUMMARY:
- This food was eaten {times_eaten} times in the analysis period
- Symptoms occurred after eating it {symptom_count} times
- Confidence level: {confidence_level}

TIMING OF SYMPTOMS:
- Within 2 hours: {ingredient_data.get("immediate_total", 0)} times
- 4-24 hours later: {ingredient_data.get("delayed_total", 0)} times
- More than 24 hours later: {ingredient_data.get("cumulative_total", 0)} times

SYMPTOMS EXPERIENCED:"""

        for symptom in ingredient_data.get("associated_symptoms", []):
            severity = symptom.get("severity_avg", 0)
            severity_desc = (
                "mild" if severity < 4 else "moderate" if severity < 7 else "severe"
            )
            formatted += f"""
- {symptom.get("name", "Unknown")}: {symptom.get("frequency", 0)} times, typically {severity_desc}, usually {symptom.get("lag_hours", 0):.0f} hours after eating"""

        return formatted

    def _format_meal_history(self, meal_history: list) -> str:
        """Format meal history for context in AI analysis."""
        if not meal_history:
            return "No meal history available."

        formatted = []
        for meal in meal_history[:10]:  # Limit to 10 meals
            ingredients = ", ".join(
                i.get("name", "unknown") for i in meal.get("ingredients", [])
            )
            formatted.append(f"- {meal.get('name', 'Meal')}: {ingredients}")

        return "\n".join(formatted)

    def _format_correlation_data(self, correlation_data: list[dict]) -> str:
        """
        Format correlation data for AI analysis.

        Args:
            correlation_data: Raw correlation statistics from DiagnosisService

        Returns:
            Formatted string representation for AI consumption
        """
        formatted = "CORRELATION DATA:\n\n"

        for i, item in enumerate(correlation_data, 1):
            formatted += (
                f"{i}. {item['ingredient_name']} ({item.get('state', 'unknown')})\n"
            )
            formatted += f"   Times eaten: {item['times_eaten']}\n"
            formatted += (
                f"   Symptom occurrences: {item['total_symptom_occurrences']}\n"
            )
            formatted += "   Temporal windows:\n"
            formatted += (
                f"     - Immediate (0-2hr): {item['immediate_total']} occurrences\n"
            )
            formatted += (
                f"     - Delayed (4-24hr): {item['delayed_total']} occurrences\n"
            )
            formatted += (
                f"     - Cumulative (24hr+): {item['cumulative_total']} occurrences\n"
            )
            formatted += "   Associated symptoms:\n"
            for symptom in item.get("associated_symptoms", []):
                formatted += f"     - {symptom['name']}: severity {symptom['severity_avg']:.1f}/10, "
                formatted += f"frequency {symptom['frequency']}, "
                formatted += f"avg lag {symptom['lag_hours']:.1f}hr\n"
            formatted += "\n"

        return formatted

    def _estimate_request_tokens(self, formatted_data: str, system_prompt: str) -> int:
        """
        Rough estimate of request tokens.
        Claude uses ~4 characters per token for English text.

        Returns:
            Estimated token count
        """
        total_chars = (
            len(system_prompt) + len(formatted_data) + 200
        )  # 200 for message overhead
        return total_chars // 4

    def _validate_request_size(
        self, formatted_data: str, system_prompt: str, max_tokens: int = 100000
    ):
        """
        Validate request size before sending to API.

        Args:
            formatted_data: Formatted correlation data
            system_prompt: System prompt text
            max_tokens: Maximum allowed tokens (default 100k for Claude Sonnet)

        Raises:
            ValueError: If request is too large
        """
        estimated_tokens = self._estimate_request_tokens(formatted_data, system_prompt)

        if estimated_tokens > max_tokens:
            raise ValueError(
                f"Request too large: ~{estimated_tokens} tokens (max {max_tokens}). "
                f"Try reducing date range or limiting number of meals/symptoms analyzed."
            )

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _load_image_base64(self, image_path: str) -> str:
        """Load image file and encode as base64."""
        with open(image_path, "rb") as f:
            return base64.standard_b64encode(f.read()).decode("utf-8")

    def _get_media_type(self, image_path: str) -> str:
        """Determine media type from file extension."""
        suffix = Path(image_path).suffix.lower()
        media_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return media_types.get(suffix, "image/jpeg")


# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================


class ServiceUnavailableError(Exception):
    """AI service is temporarily unavailable."""

    pass


class RateLimitError(Exception):
    """Rate limit exceeded."""

    pass
