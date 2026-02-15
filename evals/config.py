"""Evals configuration."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class EvalConfig:
    """Configuration for an evaluation run."""

    model: str
    eval_type: str
    dataset_path: Path = field(default_factory=lambda: Path("evals/datasets"))
    use_cache: bool = True
    sample_size: Optional[int] = None  # None = all test cases
    parallel: int = 1
    verbose: bool = False
    temperature: float = 0.0
    use_llm_judge: bool = True  # Use LLM-as-judge for soft scoring (meal_analysis)


# Default models
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

# Metric targets
METRIC_TARGETS = {
    "meal_analysis": {
        "precision": 0.80,
        "recall": 0.75,
        "f1": 0.77,
        "state_accuracy": 0.80,
        "meal_name_similarity": 0.70,
    },
    "meal_validation": {
        "accuracy": 0.95,
        "true_positive_rate": 0.98,
        "true_negative_rate": 0.90,
    },
    "symptom_elaboration": {
        "completeness": 1.0,
        "clinical_tone": 1.0,
    },
    "episode_continuation": {
        "accuracy": 0.85,
    },
}

# Fuzzy matching threshold for ingredient names
INGREDIENT_MATCH_THRESHOLD = 0.8

# Qualifiers to strip from ingredient names during normalization
INGREDIENT_QUALIFIERS = [
    "fresh",
    "dried",
    "ground",
    "sliced",
    "chopped",
    "diced",
    "minced",
    "grated",
    "crushed",
    "whole",
    "large",
    "small",
    "medium",
    "thin",
    "thick",
    "frozen",
    "canned",
    "tinned",
    "organic",
    "free-range",
]
