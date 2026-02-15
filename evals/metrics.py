"""Scoring functions for evaluations."""

import json
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

from .config import INGREDIENT_MATCH_THRESHOLD, INGREDIENT_QUALIFIERS
from .judge_prompts import INGREDIENT_MATCH_JUDGE_PROMPT, INGREDIENT_MATCH_USER_TEMPLATE


def normalize_ingredient(name: str) -> str:
    """Normalize ingredient name for comparison.

    - Lowercase
    - Strip whitespace
    - Remove common qualifiers (fresh, dried, sliced, etc.)
    - Singularize simple plurals
    """
    name = name.lower().strip()

    # Remove qualifiers
    for qualifier in INGREDIENT_QUALIFIERS:
        name = name.replace(qualifier, "").strip()

    # Clean up multiple spaces
    name = " ".join(name.split())

    # Simple singularization (handles most cases)
    if name.endswith("ies"):
        name = name[:-3] + "y"  # berries -> berry
    elif name.endswith("oes"):
        name = name[:-2]  # tomatoes -> tomato
    elif name.endswith("es") and not name.endswith("cheese"):
        name = name[:-2]  # peaches -> peach
    elif name.endswith("s") and not name.endswith("ss"):
        name = name[:-1]  # carrots -> carrot

    return name


def ingredient_matches(
    predicted: str, expected: dict, threshold: float = INGREDIENT_MATCH_THRESHOLD
) -> bool:
    """Check if predicted ingredient matches expected (with variants).

    Args:
        predicted: The predicted ingredient name
        expected: Dict with 'name' and optional 'name_variants' list
        threshold: Minimum similarity ratio for fuzzy matching

    Returns:
        True if the predicted name matches the expected name or any variant
    """
    pred_norm = normalize_ingredient(predicted)

    # Check exact match with primary name
    exp_norm = normalize_ingredient(expected["name"])
    if pred_norm == exp_norm:
        return True

    # Fuzzy match with primary name
    ratio = SequenceMatcher(None, pred_norm, exp_norm).ratio()
    if ratio >= threshold:
        return True

    # Check variants
    for variant in expected.get("name_variants", []):
        variant_norm = normalize_ingredient(variant)
        if pred_norm == variant_norm:
            return True

        # Fuzzy match for variants
        ratio = SequenceMatcher(None, pred_norm, variant_norm).ratio()
        if ratio >= threshold:
            return True

    return False


async def llm_judge_ingredient_match(
    predicted: str,
    expected_list: list[dict],
    claude_service,
    cache_manager=None,
) -> dict:
    """Use Haiku to score ingredient match (0, 0.5, or 1.0).

    Args:
        predicted: Predicted ingredient name
        expected_list: List of expected ingredient dicts with 'name' and 'name_variants'
        claude_service: ClaudeService instance for API calls
        cache_manager: Optional cache manager for API response caching

    Returns:
        dict with keys:
            - score: float (0, 0.5, or 1.0)
            - matched_to: str or None (name of matched expected ingredient)
            - reasoning: str (brief explanation)
    """
    # Format expected ingredients for the prompt
    expected_formatted = "\n".join(
        f"- {exp['name']}" + (f" (variants: {', '.join(exp.get('name_variants', []))})"
                              if exp.get('name_variants') else "")
        for exp in expected_list
    )

    user_message = INGREDIENT_MATCH_USER_TEMPLATE.format(
        predicted=predicted,
        expected_list=expected_formatted,
    )

    # Check cache first
    cache_key = None
    if cache_manager:
        cached = cache_manager.get(
            "llm_judge_ingredient",
            predicted=predicted,
            expected_hash=hash(expected_formatted),
        )
        if cached:
            return cached

    # Call Haiku for judgment
    try:
        response = claude_service.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            system=INGREDIENT_MATCH_JUDGE_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        raw_response = response.content[0].text.strip()

        # Parse JSON response
        try:
            result = json.loads(raw_response)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            if "{" in raw_response and "}" in raw_response:
                json_str = raw_response[raw_response.index("{"):raw_response.rindex("}") + 1]
                result = json.loads(json_str)
            else:
                # Fallback to string matching
                return {
                    "score": 0.0,
                    "matched_to": None,
                    "reasoning": f"Failed to parse LLM response: {raw_response[:100]}",
                }

        # Validate and normalize score
        score = result.get("score", 0)
        if score not in [0, 0.5, 1, 1.0]:
            # Round to nearest valid score
            if score >= 0.75:
                score = 1.0
            elif score >= 0.25:
                score = 0.5
            else:
                score = 0.0
        else:
            score = float(score)

        output = {
            "score": score,
            "matched_to": result.get("matched_to"),
            "reasoning": result.get("reasoning", ""),
        }

        # Cache the result
        if cache_manager:
            cache_manager.set(
                "llm_judge_ingredient",
                output,
                predicted=predicted,
                expected_hash=hash(expected_formatted),
            )

        return output

    except Exception as e:
        # On API error, fallback to string matching
        for exp in expected_list:
            if ingredient_matches(predicted, exp):
                return {
                    "score": 1.0,
                    "matched_to": exp["name"],
                    "reasoning": f"Fallback string match (API error: {str(e)[:50]})",
                }
        return {
            "score": 0.0,
            "matched_to": None,
            "reasoning": f"No match (API error: {str(e)[:50]})",
        }


@dataclass
class SoftMatchResult:
    """Result of soft matching for a single predicted ingredient."""
    predicted: str
    score: float
    matched_to: Optional[str]
    reasoning: str


@dataclass
class MealAnalysisScore:
    """Scores for a single meal analysis prediction."""

    precision: float
    recall: float
    f1: float
    state_accuracy: float
    meal_name_similarity: float
    ingredient_details: dict


def score_meal_analysis(
    predicted: dict, expected: dict, fuzzy_threshold: float = INGREDIENT_MATCH_THRESHOLD
) -> MealAnalysisScore:
    """Score a single meal analysis prediction.

    Args:
        predicted: AI prediction with 'meal_name' and 'ingredients' list
        expected: Ground truth with 'meal_name', 'meal_name_alternatives', and 'ingredients' list

    Returns:
        MealAnalysisScore with precision, recall, F1, state accuracy, and details
    """
    pred_ingredients = predicted.get("ingredients", [])
    exp_ingredients = expected.get("ingredients", [])

    # Track matches
    matched_expected: set[int] = set()
    true_positives: list[dict] = []
    false_positives: list[dict] = []
    state_matches = 0

    for pred in pred_ingredients:
        pred_name = pred.get("name", "") if isinstance(pred, dict) else pred
        matched = False

        for i, exp in enumerate(exp_ingredients):
            if i in matched_expected:
                continue

            if ingredient_matches(pred_name, exp, fuzzy_threshold):
                matched = True
                matched_expected.add(i)
                true_positives.append({"predicted": pred, "expected": exp})

                # Check state match
                pred_state = pred.get("state") if isinstance(pred, dict) else None
                if pred_state and pred_state == exp.get("state"):
                    state_matches += 1
                break

        if not matched:
            false_positives.append(pred)

    # False negatives: required expected ingredients not matched
    false_negatives = [
        exp
        for i, exp in enumerate(exp_ingredients)
        if i not in matched_expected and exp.get("required", True)
    ]

    tp = len(true_positives)
    fp = len(false_positives)
    fn = len(false_negatives)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    state_accuracy = state_matches / tp if tp > 0 else 0.0

    # Meal name similarity
    pred_meal_name = predicted.get("meal_name", "").lower()
    exp_meal_name = expected.get("meal_name", "").lower()

    # Check against primary name and alternatives
    best_similarity = SequenceMatcher(None, pred_meal_name, exp_meal_name).ratio()
    for alt in expected.get("meal_name_alternatives", []):
        alt_sim = SequenceMatcher(None, pred_meal_name, alt.lower()).ratio()
        best_similarity = max(best_similarity, alt_sim)

    return MealAnalysisScore(
        precision=precision,
        recall=recall,
        f1=f1,
        state_accuracy=state_accuracy,
        meal_name_similarity=best_similarity,
        ingredient_details={
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
        },
    )


async def score_meal_analysis_soft(
    predicted: dict,
    expected: dict,
    claude_service,
    cache_manager=None,
    verbose: bool = False,
) -> MealAnalysisScore:
    """Score a meal analysis prediction using soft LLM-based matching.

    Uses Haiku as an LLM judge to score each predicted ingredient against
    the expected list with scores of 0, 0.5, or 1.0.

    Soft Precision = sum(match_scores) / num_predicted
    Soft Recall = sum(best_match_scores) / num_expected
    Soft F1 = harmonic mean

    Args:
        predicted: AI prediction with 'meal_name' and 'ingredients' list
        expected: Ground truth with 'meal_name', 'meal_name_alternatives', and 'ingredients' list
        claude_service: ClaudeService instance for LLM judge API calls
        cache_manager: Optional cache manager for API response caching
        verbose: If True, print per-ingredient match details

    Returns:
        MealAnalysisScore with soft precision, recall, F1, state accuracy, and details
    """
    pred_ingredients = predicted.get("ingredients", [])
    exp_ingredients = expected.get("ingredients", [])

    # Get only required expected ingredients for recall calculation
    required_exp = [exp for exp in exp_ingredients if exp.get("required", True)]

    # Score each predicted ingredient
    prediction_scores: list[SoftMatchResult] = []
    matched_expected_scores: dict[int, float] = {}  # Track best score per expected ingredient

    for pred in pred_ingredients:
        pred_name = pred.get("name", "") if isinstance(pred, dict) else pred

        # Get LLM judgment
        result = await llm_judge_ingredient_match(
            predicted=pred_name,
            expected_list=exp_ingredients,
            claude_service=claude_service,
            cache_manager=cache_manager,
        )

        soft_result = SoftMatchResult(
            predicted=pred_name,
            score=result["score"],
            matched_to=result["matched_to"],
            reasoning=result["reasoning"],
        )
        prediction_scores.append(soft_result)

        if verbose:
            print(f"      {pred_name} -> {result['matched_to'] or 'NO MATCH'} ({result['score']})")

        # Track best score for each expected ingredient (for recall)
        if result["matched_to"] and result["score"] > 0:
            for i, exp in enumerate(exp_ingredients):
                if exp["name"] == result["matched_to"]:
                    current_best = matched_expected_scores.get(i, 0)
                    matched_expected_scores[i] = max(current_best, result["score"])
                    break

    # Calculate soft precision: sum of match scores / number of predictions
    if pred_ingredients:
        soft_precision = sum(r.score for r in prediction_scores) / len(pred_ingredients)
    else:
        soft_precision = 0.0

    # Calculate soft recall: sum of best match scores for required ingredients / number required
    if required_exp:
        recall_sum = 0.0
        for i, exp in enumerate(exp_ingredients):
            if exp.get("required", True):
                recall_sum += matched_expected_scores.get(i, 0.0)
        soft_recall = recall_sum / len(required_exp)
    else:
        soft_recall = 0.0

    # Calculate soft F1
    if (soft_precision + soft_recall) > 0:
        soft_f1 = 2 * soft_precision * soft_recall / (soft_precision + soft_recall)
    else:
        soft_f1 = 0.0

    # State accuracy: count full matches where state also matches
    state_matches = 0
    full_matches = 0
    for pred, result in zip(pred_ingredients, prediction_scores):
        if result.score >= 1.0 and result.matched_to:
            full_matches += 1
            pred_state = pred.get("state") if isinstance(pred, dict) else None
            # Find the matched expected ingredient to compare state
            for exp in exp_ingredients:
                if exp["name"] == result.matched_to:
                    if pred_state and pred_state == exp.get("state"):
                        state_matches += 1
                    break

    state_accuracy = state_matches / full_matches if full_matches > 0 else 0.0

    # Meal name similarity (same as hard matching)
    pred_meal_name = predicted.get("meal_name", "").lower()
    exp_meal_name = expected.get("meal_name", "").lower()

    best_similarity = SequenceMatcher(None, pred_meal_name, exp_meal_name).ratio()
    for alt in expected.get("meal_name_alternatives", []):
        alt_sim = SequenceMatcher(None, pred_meal_name, alt.lower()).ratio()
        best_similarity = max(best_similarity, alt_sim)

    # Build detailed results for analysis
    true_positives = [
        {"predicted": r.predicted, "score": r.score, "matched_to": r.matched_to, "reasoning": r.reasoning}
        for r in prediction_scores if r.score >= 0.5
    ]
    false_positives = [
        {"predicted": r.predicted, "score": r.score, "reasoning": r.reasoning}
        for r in prediction_scores if r.score == 0.0
    ]
    false_negatives = [
        exp for i, exp in enumerate(exp_ingredients)
        if exp.get("required", True) and matched_expected_scores.get(i, 0) == 0
    ]

    return MealAnalysisScore(
        precision=soft_precision,
        recall=soft_recall,
        f1=soft_f1,
        state_accuracy=state_accuracy,
        meal_name_similarity=best_similarity,
        ingredient_details={
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "soft_scoring": True,
            "prediction_scores": [
                {"predicted": r.predicted, "score": r.score, "matched_to": r.matched_to}
                for r in prediction_scores
            ],
        },
    )


def score_meal_validation(predicted: bool, expected: bool) -> dict:
    """Score a single meal validation prediction.

    Args:
        predicted: AI prediction (True = is food)
        expected: Ground truth

    Returns:
        Dict with correct, is_true_positive, is_true_negative, etc.
    """
    correct = predicted == expected
    return {
        "correct": correct,
        "is_true_positive": predicted and expected,
        "is_true_negative": not predicted and not expected,
        "is_false_positive": predicted and not expected,
        "is_false_negative": not predicted and expected,
    }


def aggregate_meal_analysis_scores(results: list[dict]) -> dict:
    """Compute aggregate metrics from individual meal analysis results.

    Args:
        results: List of dicts with 'score' containing individual metrics

    Returns:
        Aggregate metrics with mean, min, max for each metric
    """
    if not results:
        return {}

    metrics = ["precision", "recall", "f1", "state_accuracy", "meal_name_similarity"]
    aggregates = {}

    for metric in metrics:
        values = [r["score"][metric] for r in results if "score" in r]
        if values:
            aggregates[f"mean_{metric}"] = sum(values) / len(values)
            aggregates[f"min_{metric}"] = min(values)
            aggregates[f"max_{metric}"] = max(values)

    return aggregates
