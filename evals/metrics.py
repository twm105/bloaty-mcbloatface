"""Scoring functions for evaluations."""

from dataclasses import dataclass
from difflib import SequenceMatcher

from .config import INGREDIENT_MATCH_THRESHOLD, INGREDIENT_QUALIFIERS


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
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
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
