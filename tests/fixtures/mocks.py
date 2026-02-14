"""
Mock services for testing AI functionality.

These mocks provide deterministic responses for testing without API calls.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, AsyncIterator


class MockClaudeService:
    """
    Mock Claude service for testing AI functionality.

    Provides configurable responses for all ClaudeService methods.
    Configure responses per-test by setting attributes on the mock instance.
    """

    def __init__(self):
        # Default model names
        self.haiku_model = "claude-3-haiku-20240307"
        self.sonnet_model = "claude-sonnet-4-5-20250929"

        # Track method calls for assertions
        self.calls: Dict[str, List[Dict]] = {}

        # Configurable responses (set per test)
        self._validate_meal_image_response = True
        self._analyze_meal_image_response: Optional[Dict] = None
        self._elaborate_symptom_tags_response: Optional[Dict] = None
        self._detect_episode_continuation_response: Optional[Dict] = None
        self._diagnose_correlations_response: Optional[Dict] = None
        self._diagnose_single_ingredient_response: Optional[Dict] = None
        self._classify_root_cause_response: Optional[Dict] = None

        # Error simulation
        self._raise_error: Optional[Exception] = None

    def _record_call(self, method: str, **kwargs):
        """Record a method call for assertion."""
        if method not in self.calls:
            self.calls[method] = []
        self.calls[method].append(
            {"timestamp": datetime.utcnow().isoformat(), "kwargs": kwargs}
        )

    def reset(self):
        """Reset all recorded calls and responses."""
        self.calls = {}
        self._raise_error = None

    def set_error(self, error: Exception):
        """Set an error to raise on next call."""
        self._raise_error = error

    # =========================================================================
    # Meal Image Analysis
    # =========================================================================

    async def validate_meal_image(self, image_path: str) -> bool:
        """Mock image validation."""
        self._record_call("validate_meal_image", image_path=image_path)

        if self._raise_error:
            error = self._raise_error
            self._raise_error = None
            raise error

        return self._validate_meal_image_response

    def set_validate_meal_image_response(self, is_valid: bool):
        """Configure validate_meal_image response."""
        self._validate_meal_image_response = is_valid

    async def analyze_meal_image(
        self, image_path: str, user_notes: Optional[str] = None
    ) -> dict:
        """Mock meal image analysis."""
        self._record_call(
            "analyze_meal_image", image_path=image_path, user_notes=user_notes
        )

        if self._raise_error:
            error = self._raise_error
            self._raise_error = None
            raise error

        if self._analyze_meal_image_response is not None:
            return self._analyze_meal_image_response

        # Default response
        return {
            "meal_name": "Test Meal",
            "ingredients": [
                {
                    "name": "chicken breast",
                    "state": "cooked",
                    "quantity": "150g",
                    "confidence": 0.92,
                },
                {
                    "name": "rice",
                    "state": "cooked",
                    "quantity": "1 cup",
                    "confidence": 0.88,
                },
                {
                    "name": "broccoli",
                    "state": "cooked",
                    "quantity": "1/2 cup",
                    "confidence": 0.85,
                },
            ],
            "raw_response": "{}",
            "model": self.haiku_model,
        }

    def set_analyze_meal_image_response(self, response: Dict):
        """Configure analyze_meal_image response."""
        self._analyze_meal_image_response = response

    # =========================================================================
    # Symptom Elaboration & Episode Detection
    # =========================================================================

    async def elaborate_symptom_tags(
        self,
        tags: list,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        user_notes: Optional[str] = None,
    ) -> dict:
        """Mock symptom elaboration."""
        self._record_call(
            "elaborate_symptom_tags",
            tags=tags,
            start_time=start_time,
            end_time=end_time,
            user_notes=user_notes,
        )

        if self._raise_error:
            error = self._raise_error
            self._raise_error = None
            raise error

        if self._elaborate_symptom_tags_response is not None:
            return self._elaborate_symptom_tags_response

        # Generate default response based on tags
        tag_names = [t.get("name", "symptom") for t in tags]
        severity = max(t.get("severity", 5) for t in tags)
        severity_word = (
            "mild" if severity < 4 else "moderate" if severity < 7 else "severe"
        )

        return {
            "elaboration": (
                f"Patient experienced {severity_word} {', '.join(tag_names)}. "
                f"Symptoms were rated {severity}/10 in severity. "
                "Recommend monitoring for recurrence and potential dietary triggers."
            ),
            "raw_response": "",
            "model": self.sonnet_model,
        }

    def set_elaborate_symptom_tags_response(self, response: Dict):
        """Configure elaborate_symptom_tags response."""
        self._elaborate_symptom_tags_response = response

    async def elaborate_symptom_tags_streaming(
        self,
        tags: list,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        user_notes: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Mock streaming symptom elaboration."""
        self._record_call(
            "elaborate_symptom_tags_streaming",
            tags=tags,
            start_time=start_time,
            end_time=end_time,
            user_notes=user_notes,
        )

        if self._raise_error:
            error = self._raise_error
            self._raise_error = None
            raise error

        # Get response (use non-streaming method's response)
        response = await self.elaborate_symptom_tags(
            tags, start_time, end_time, user_notes
        )

        # Yield chunks
        text = response.get("elaboration", "")
        chunk_size = 20
        for i in range(0, len(text), chunk_size):
            yield text[i : i + chunk_size]

    async def detect_episode_continuation(
        self, current_tags: list, current_time: datetime, previous_symptom: dict
    ) -> dict:
        """Mock episode continuation detection."""
        self._record_call(
            "detect_episode_continuation",
            current_tags=current_tags,
            current_time=current_time,
            previous_symptom=previous_symptom,
        )

        if self._raise_error:
            error = self._raise_error
            self._raise_error = None
            raise error

        if self._detect_episode_continuation_response is not None:
            return self._detect_episode_continuation_response

        # Default: check if same symptom types within reasonable time
        current_names = {t.get("name", "").lower() for t in current_tags}
        prev_tags = previous_symptom.get("tags", [])
        prev_names = {t.get("name", "").lower() for t in prev_tags}

        is_continuation = bool(current_names & prev_names)

        return {
            "is_continuation": is_continuation,
            "confidence": 0.85 if is_continuation else 0.15,
            "reasoning": (
                "Similar symptoms reported within episode window."
                if is_continuation
                else "Different symptom pattern detected."
            ),
        }

    def set_detect_episode_continuation_response(self, response: Dict):
        """Configure detect_episode_continuation response."""
        self._detect_episode_continuation_response = response

    async def detect_ongoing_symptom(
        self, previous_symptom: dict, current_symptom: dict
    ) -> dict:
        """Mock ongoing symptom detection."""
        self._record_call(
            "detect_ongoing_symptom",
            previous_symptom=previous_symptom,
            current_symptom=current_symptom,
        )

        if self._raise_error:
            error = self._raise_error
            self._raise_error = None
            raise error

        # Simple logic: same symptom name = ongoing
        prev_name = previous_symptom.get("name", "").lower()
        curr_name = current_symptom.get("name", "").lower()
        is_ongoing = prev_name == curr_name

        return {
            "is_ongoing": is_ongoing,
            "confidence": 0.9 if is_ongoing else 0.1,
            "reasoning": "Symptom names match."
            if is_ongoing
            else "Different symptoms.",
        }

    # =========================================================================
    # Diagnosis
    # =========================================================================

    async def diagnose_correlations(
        self, correlation_data: list, web_search_enabled: bool = True
    ) -> dict:
        """Mock correlation diagnosis."""
        self._record_call(
            "diagnose_correlations",
            correlation_data=correlation_data,
            web_search_enabled=web_search_enabled,
        )

        if self._raise_error:
            error = self._raise_error
            self._raise_error = None
            raise error

        if self._diagnose_correlations_response is not None:
            return self._diagnose_correlations_response

        # Generate mock analysis for each ingredient
        analyses = []
        for item in correlation_data:
            ingredient_name = item.get("ingredient_name", "Unknown")
            analyses.append(
                {
                    "ingredient_name": ingredient_name,
                    "medical_context": (
                        f"{ingredient_name} is known to cause digestive issues in "
                        "some individuals, particularly those with sensitivities."
                    ),
                    "interpretation": (
                        f"The correlation data suggests a potential link between "
                        f"{ingredient_name} consumption and reported symptoms."
                    ),
                    "recommendations": (
                        f"Consider temporarily eliminating {ingredient_name} "
                        "from your diet and monitoring symptoms."
                    ),
                    "citations": [
                        {
                            "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
                            "title": f"Food Intolerance: {ingredient_name}",
                            "source_type": "medical_journal",
                            "snippet": f"Study on {ingredient_name} sensitivity.",
                            "relevance": 0.85,
                        }
                    ],
                }
            )

        return {
            "ingredient_analyses": analyses,
            "overall_summary": "Analysis complete. Potential triggers identified.",
            "caveats": [
                "This analysis is based on correlation, not causation.",
                "Consult a healthcare professional for diagnosis.",
            ],
            "usage_stats": {
                "input_tokens": 1500,
                "cached_tokens": 0,
                "cache_hit": False,
            },
        }

    def set_diagnose_correlations_response(self, response: Dict):
        """Configure diagnose_correlations response."""
        self._diagnose_correlations_response = response

    async def diagnose_single_ingredient(
        self,
        ingredient_data: dict,
        user_meal_history: list,
        web_search_enabled: bool = True,
    ) -> dict:
        """Mock single ingredient diagnosis."""
        self._record_call(
            "diagnose_single_ingredient",
            ingredient_data=ingredient_data,
            user_meal_history=user_meal_history,
            web_search_enabled=web_search_enabled,
        )

        if self._raise_error:
            error = self._raise_error
            self._raise_error = None
            raise error

        if self._diagnose_single_ingredient_response is not None:
            return self._diagnose_single_ingredient_response

        ingredient_name = ingredient_data.get("ingredient_name", "Unknown")

        return {
            "diagnosis_summary": (
                f"{ingredient_name} shows correlation with reported symptoms. "
                "This could indicate a potential sensitivity."
            ),
            "recommendations_summary": (
                f"Consider an elimination diet to confirm {ingredient_name} sensitivity. "
                "Keep a food diary to track symptoms."
            ),
            "processing_suggestions": {
                "cooked_vs_raw": "Cooking may reduce symptom severity.",
                "alternatives": ["substitute A", "substitute B"],
            },
            "alternative_meals": [],
            "citations": [
                {
                    "url": "https://www.nih.gov/example",
                    "title": "Food Sensitivity Overview",
                    "source_type": "nih",
                    "snippet": "General information on food sensitivities.",
                }
            ],
            "usage_stats": {
                "input_tokens": 800,
                "output_tokens": 400,
                "cached_tokens": 0,
                "cache_hit": False,
            },
        }

    def set_diagnose_single_ingredient_response(self, response: Dict):
        """Configure diagnose_single_ingredient response."""
        self._diagnose_single_ingredient_response = response

    async def classify_root_cause(
        self,
        ingredient_data: dict,
        cooccurrence_data: list,
        medical_grounding: str,
        web_search_enabled: bool = True,
    ) -> dict:
        """Mock root cause classification."""
        self._record_call(
            "classify_root_cause",
            ingredient_data=ingredient_data,
            cooccurrence_data=cooccurrence_data,
            medical_grounding=medical_grounding,
            web_search_enabled=web_search_enabled,
        )

        if self._raise_error:
            error = self._raise_error
            self._raise_error = None
            raise error

        if self._classify_root_cause_response is not None:
            return self._classify_root_cause_response

        # Default: classify as root cause unless high cooccurrence
        is_root_cause = True
        confounded_by = None

        for cooc in cooccurrence_data:
            if cooc.get("conditional_probability", 0) > 0.8:
                is_root_cause = False
                confounded_by = cooc.get("with_ingredient_name")
                break

        return {
            "root_cause": is_root_cause,
            "discard_justification": None
            if is_root_cause
            else (f"High co-occurrence with {confounded_by}"),
            "confounded_by": confounded_by,
            "medical_reasoning": (
                "Medical evidence supports this as a likely trigger."
                if is_root_cause
                else f"Likely confounded by {confounded_by}."
            ),
            "usage_stats": {"input_tokens": 500, "output_tokens": 200},
        }

    def set_classify_root_cause_response(self, response: Dict):
        """Configure classify_root_cause response."""
        self._classify_root_cause_response = response

    # =========================================================================
    # Symptom Clarification
    # =========================================================================

    async def clarify_symptom(
        self, raw_description: str, clarification_history: Optional[list] = None
    ) -> dict:
        """Mock symptom clarification."""
        self._record_call(
            "clarify_symptom",
            raw_description=raw_description,
            clarification_history=clarification_history,
        )

        if self._raise_error:
            error = self._raise_error
            self._raise_error = None
            raise error

        # Count questions asked
        history = clarification_history or []
        num_questions = len(history)

        if num_questions < 2:
            # Ask another question
            questions = [
                "When did you first notice the symptoms?",
                "How severe would you rate the symptoms on a scale of 1-10?",
                "Did you notice any triggers?",
            ]
            return {
                "mode": "question",
                "question": questions[num_questions % len(questions)],
            }
        else:
            # Complete with structured data
            return {
                "mode": "complete",
                "structured": {
                    "type": "bloating",
                    "severity": 6,
                    "notes": raw_description,
                },
            }

    # =========================================================================
    # Pattern Analysis
    # =========================================================================

    async def analyze_patterns(
        self,
        meals_data: str,
        symptoms_data: str,
        analysis_question: str = "Identify ingredients that may be correlated with symptoms.",
    ) -> dict:
        """Mock pattern analysis."""
        self._record_call(
            "analyze_patterns",
            meals_data=meals_data,
            symptoms_data=symptoms_data,
            analysis_question=analysis_question,
        )

        if self._raise_error:
            error = self._raise_error
            self._raise_error = None
            raise error

        return {
            "analysis": (
                "## Pattern Analysis\n\n"
                "Based on the meal and symptom data:\n\n"
                "- Potential correlation identified\n"
                "- Recommend further investigation\n"
            ),
            "model": self.sonnet_model,
            "cache_hit": False,
            "input_tokens": 2000,
            "cached_tokens": 0,
        }


# Helper functions for common test scenarios
def create_mock_with_error(error: Exception) -> MockClaudeService:
    """Create a mock that raises an error on any call."""
    mock = MockClaudeService()
    mock.set_error(error)
    return mock


def create_mock_for_meal_analysis(
    ingredients: List[Dict[str, Any]], meal_name: str = "Test Meal"
) -> MockClaudeService:
    """Create a mock configured for meal analysis testing."""
    mock = MockClaudeService()
    mock.set_analyze_meal_image_response(
        {
            "meal_name": meal_name,
            "ingredients": ingredients,
            "raw_response": "{}",
            "model": mock.haiku_model,
        }
    )
    return mock


def create_mock_for_diagnosis(
    is_root_cause: bool = True, confounded_by: Optional[str] = None
) -> MockClaudeService:
    """Create a mock configured for diagnosis testing."""
    mock = MockClaudeService()
    mock.set_classify_root_cause_response(
        {
            "root_cause": is_root_cause,
            "discard_justification": None
            if is_root_cause
            else f"Confounded by {confounded_by}",
            "confounded_by": confounded_by,
            "medical_reasoning": "Test reasoning",
            "usage_stats": {"input_tokens": 100, "output_tokens": 50},
        }
    )
    return mock
