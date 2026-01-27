"""
Claude AI integration service for meal analysis, symptom clarification, and pattern analysis.

This service provides three core AI capabilities:
1. Meal image analysis with ingredient detection (Haiku)
2. Conversational symptom clarification (Sonnet)
3. Pattern analysis with prompt caching (Sonnet)
"""

import json
import base64
from pathlib import Path
from typing import Optional, Union
from datetime import datetime
from uuid import UUID

from anthropic import Anthropic
import anthropic

from app.config import settings
from app.services.prompts import (
    MEAL_VALIDATION_SYSTEM_PROMPT,
    MEAL_ANALYSIS_SYSTEM_PROMPT,
    SYMPTOM_CLARIFICATION_SYSTEM_PROMPT,
    build_cached_analysis_context
)


class ClaudeService:
    """Centralized Claude API integration for all AI features."""

    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.haiku_model = settings.haiku_model
        self.sonnet_model = settings.sonnet_model

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
                                    "data": image_data
                                }
                            },
                            {
                                "type": "text",
                                "text": "Is this a photo of food or a meal? Answer only YES or NO."
                            }
                        ]
                    }
                ],
                system=MEAL_VALIDATION_SYSTEM_PROMPT
            )

            answer = response.content[0].text.strip().upper()
            return answer == "YES"

        except anthropic.APIConnectionError as e:
            raise ServiceUnavailableError("AI service temporarily unavailable") from e
        except anthropic.RateLimitError as e:
            raise RateLimitError("Too many requests, please try again in 1 minute") from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                raise ServiceUnavailableError("AI service error") from e
            raise ValueError(f"Request error: {e.message}") from e
        except Exception as e:
            raise ValueError(f"Image validation failed: {str(e)}") from e

    async def analyze_meal_image(
        self,
        image_path: str,
        user_notes: Optional[str] = None
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
                        "data": image_data
                    }
                },
                {
                    "type": "text",
                    "text": "Analyze this meal and identify all visible ingredients."
                }
            ]

            if user_notes:
                user_message.append({
                    "type": "text",
                    "text": f"User notes: {user_notes}"
                })

            # Call Claude
            response = self.client.messages.create(
                model=self.haiku_model,
                max_tokens=1024,
                messages=[{"role": "user", "content": user_message}],
                system=MEAL_ANALYSIS_SYSTEM_PROMPT
            )

            raw_response = response.content[0].text

            # Parse JSON response - handle markdown code blocks
            try:
                # First try direct parsing
                if "```json" in raw_response or "```" in raw_response:
                    # Extract from markdown code block
                    json_str = raw_response
                    if "```json" in json_str:
                        json_str = json_str.split("```json")[1]
                    elif "```" in json_str:
                        json_str = json_str.split("```")[1]
                    json_str = json_str.split("```")[0].strip()
                    parsed = json.loads(json_str)
                else:
                    parsed = json.loads(raw_response)

                ingredients = parsed.get("ingredients", [])
                meal_name = parsed.get("meal_name", "Untitled Meal")
            except json.JSONDecodeError as e:
                raise ValueError(f"Could not parse AI response as JSON: {str(e)}")

            return {
                "meal_name": meal_name,
                "ingredients": ingredients,
                "raw_response": raw_response,
                "model": self.haiku_model
            }

        except anthropic.APIConnectionError as e:
            raise ServiceUnavailableError("AI service temporarily unavailable") from e
        except anthropic.RateLimitError as e:
            raise RateLimitError("Too many requests, please try again in 1 minute") from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                raise ServiceUnavailableError("AI service error") from e
            raise ValueError(f"Request error: {e.message}") from e
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse AI response: {str(e)}") from e

    # =========================================================================
    # SYMPTOM CLARIFICATION (Task #6)
    # =========================================================================

    async def clarify_symptom(
        self,
        raw_description: str,
        clarification_history: list = None
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
                    "content": f"My symptom description: {raw_description}"
                }
            ]

            # Add clarification Q&A to messages
            for item in clarification_history:
                if not item.get("skipped", False):
                    messages.append({
                        "role": "assistant",
                        "content": json.dumps({"mode": "question", "question": item["question"]})
                    })
                    messages.append({
                        "role": "user",
                        "content": item["answer"]
                    })
                else:
                    # User skipped this question
                    messages.append({
                        "role": "assistant",
                        "content": json.dumps({"mode": "question", "question": item["question"]})
                    })
                    messages.append({
                        "role": "user",
                        "content": "I'd prefer to skip this question."
                    })

            # Add instruction to proceed
            messages.append({
                "role": "user",
                "content": f"Questions asked so far: {len(clarification_history)}. Please proceed."
            })

            # Call Claude
            response = self.client.messages.create(
                model=self.sonnet_model,
                max_tokens=512,
                messages=messages,
                system=SYMPTOM_CLARIFICATION_SYSTEM_PROMPT
            )

            raw_response = response.content[0].text

            # Parse JSON response
            try:
                parsed = json.loads(raw_response)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown
                if "```json" in raw_response:
                    json_str = raw_response.split("```json")[1].split("```")[0].strip()
                    parsed = json.loads(json_str)
                else:
                    raise ValueError("Could not parse AI response as JSON")

            return parsed

        except anthropic.APIConnectionError as e:
            raise ServiceUnavailableError("AI service temporarily unavailable") from e
        except anthropic.RateLimitError as e:
            raise RateLimitError("Too many requests, please try again in 1 minute") from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                raise ServiceUnavailableError("AI service error") from e
            raise ValueError(f"Request error: {e.message}") from e
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse AI response: {str(e)}") from e

    # =========================================================================
    # PATTERN ANALYSIS (Task #8)
    # =========================================================================

    async def analyze_patterns(
        self,
        meals_data: str,
        symptoms_data: str,
        analysis_question: str = "Identify ingredients that may be correlated with symptoms."
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
                messages=[
                    {
                        "role": "user",
                        "content": analysis_question
                    }
                ]
            )

            analysis = response.content[0].text

            # Extract token usage for cost tracking
            usage = response.usage
            cache_hit = hasattr(usage, 'cache_read_input_tokens') and usage.cache_read_input_tokens > 0

            return {
                "analysis": analysis,
                "model": self.sonnet_model,
                "cache_hit": cache_hit,
                "input_tokens": usage.input_tokens,
                "cached_tokens": getattr(usage, 'cache_read_input_tokens', 0)
            }

        except anthropic.APIConnectionError as e:
            raise ServiceUnavailableError("AI service temporarily unavailable") from e
        except anthropic.RateLimitError as e:
            raise RateLimitError("Too many requests, please try again in 1 minute") from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                raise ServiceUnavailableError("AI service error") from e
            raise ValueError(f"Request error: {e.message}") from e

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
            ".webp": "image/webp"
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
