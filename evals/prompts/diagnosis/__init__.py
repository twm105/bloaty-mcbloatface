"""
Versioned diagnosis root cause classification prompts for experiments.

Usage:
    from evals.prompts.diagnosis import get_prompt, CURRENT_VERSION

    prompt = get_prompt("v1_baseline")
    # or
    prompt = get_prompt()  # uses CURRENT_VERSION
"""

import importlib
from typing import Optional

# The currently active prompt version (matches production)
CURRENT_VERSION = "v2_with_research"

# Available versions
VERSIONS = [
    "v1_baseline",
    "v2_with_research",
]


def get_prompt(version: Optional[str] = None) -> str:
    """
    Get the root cause classification system prompt for a specific version.

    Args:
        version: Prompt version name (e.g., "v1_baseline").
                 If None or "current", uses CURRENT_VERSION.

    Returns:
        The ROOT_CAUSE_CLASSIFICATION_PROMPT string for that version.

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
    return module.ROOT_CAUSE_CLASSIFICATION_PROMPT


def list_versions() -> list[str]:
    """Return list of available prompt versions."""
    return VERSIONS.copy()
