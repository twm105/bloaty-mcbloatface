"""
Pydantic models for validating structured JSON responses from Claude AI.

Each schema corresponds to one AI method's expected response format.
Used by _call_with_schema_retry() in ai_service.py for validation + retry.
"""

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field


# --- Meal Analysis (analyze_meal_image) ---


class IngredientSchema(BaseModel):
    name: str
    state: str  # raw|cooked|processed
    quantity: str = ""
    confidence: float = Field(ge=0, le=1)


class MealAnalysisSchema(BaseModel):
    meal_name: str = "Untitled Meal"
    ingredients: list[IngredientSchema]


# --- Symptom Clarification (clarify_symptom) - Discriminated Union ---


class StructuredSymptom(BaseModel):
    type: str
    severity: int = Field(ge=1, le=10)
    notes: str


class ClarifySymptomQuestionSchema(BaseModel):
    mode: Literal["question"]
    question: str


class ClarifySymptomCompleteSchema(BaseModel):
    mode: Literal["complete"]
    structured: StructuredSymptom


ClarifySymptomSchema = Annotated[
    ClarifySymptomQuestionSchema | ClarifySymptomCompleteSchema,
    Field(discriminator="mode"),
]


# --- Episode/Ongoing Detection (detect_episode_continuation, detect_ongoing_symptom) ---


class EpisodeContinuationSchema(BaseModel):
    is_continuation: bool
    confidence: float = Field(ge=0, le=1)
    reasoning: str


# --- Diagnosis Correlations (diagnose_correlations) ---


class CitationSchema(BaseModel):
    url: str
    title: str
    source_type: str
    snippet: str
    relevance: float = Field(ge=0, le=1, default=0.5)


class IngredientAnalysisSchema(BaseModel):
    ingredient_name: str
    confidence_assessment: str = ""
    medical_context: str = ""
    citations: list[CitationSchema] = []
    interpretation: str = ""
    recommendations: str = ""


class DiagnosisCorrelationsSchema(BaseModel):
    ingredient_analyses: list[IngredientAnalysisSchema]
    overall_summary: str = ""
    caveats: list[str] = []


# --- Single Ingredient Diagnosis (diagnose_single_ingredient) ---


class ProcessingSuggestionsSchema(BaseModel):
    cooked_vs_raw: Optional[str] = None
    alternatives: list[str] = []


class AlternativeMealSchema(BaseModel):
    meal_id: int
    name: str
    reason: str


class SingleIngredientDiagnosisSchema(BaseModel):
    diagnosis_summary: str
    recommendations_summary: str
    processing_suggestions: Optional[ProcessingSuggestionsSchema] = None
    alternative_meals: list[AlternativeMealSchema] = []
    citations: list[CitationSchema] = []


# --- Root Cause Classification (classify_root_cause) ---


class RootCauseSchema(BaseModel):
    root_cause: bool
    discard_justification: Optional[str] = None
    confounded_by: Optional[str] = None
    medical_reasoning: str
