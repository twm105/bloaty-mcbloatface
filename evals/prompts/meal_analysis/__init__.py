"""
Versioned meal analysis prompts for experiments.

Usage:
    from evals.prompts.meal_analysis import get_prompt, CURRENT_VERSION

    prompt = get_prompt("v2_recall_focus")
    # or
    prompt = get_prompt()  # uses CURRENT_VERSION
"""

import importlib
from typing import Optional

# The currently active prompt version (matches production)
CURRENT_VERSION = "v1_baseline"

# Available versions
VERSIONS = [
    "v1_baseline",
    "v2_recall_focus",
    "v3_recipe_inference",
    "v4_atomic_ingredients",
]


def get_prompt(version: Optional[str] = None) -> str:
    """
    Get the meal analysis system prompt for a specific version.

    Args:
        version: Prompt version name (e.g., "v2_recall_focus").
                 If None or "current", uses CURRENT_VERSION.

    Returns:
        The MEAL_ANALYSIS_SYSTEM_PROMPT string for that version.

    Raises:
        ValueError: If version not found.
    """
    if version is None or version == "current":
        version = CURRENT_VERSION

    if version not in VERSIONS:
        raise ValueError(
            f"Unknown prompt version: {version}. Available: {', '.join(VERSIONS)}"
        )

    module = importlib.import_module(f".{version}", package=__name__)
    return module.MEAL_ANALYSIS_SYSTEM_PROMPT


def list_versions() -> list[str]:
    """Return list of available prompt versions."""
    return VERSIONS.copy()
