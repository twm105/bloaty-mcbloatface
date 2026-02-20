"""Eval runners package."""

from .base import BaseEvalRunner
from .meal_analysis import MealAnalysisRunner
from .diagnosis_root_cause import DiagnosisRootCauseRunner

# Registry of available runners
RUNNERS = {
    "meal_analysis": MealAnalysisRunner,
    "diagnosis_root_cause": DiagnosisRootCauseRunner,
}


def get_runner(config):
    """Get the appropriate runner for the eval type.

    Args:
        config: EvalConfig with eval_type set

    Returns:
        Instantiated runner for the eval type

    Raises:
        ValueError: If eval_type is not supported
    """
    runner_class = RUNNERS.get(config.eval_type)
    if not runner_class:
        available = ", ".join(RUNNERS.keys())
        raise ValueError(
            f"Unknown eval type: {config.eval_type}. Available: {available}"
        )
    return runner_class(config)


__all__ = [
    "BaseEvalRunner",
    "MealAnalysisRunner",
    "DiagnosisRootCauseRunner",
    "get_runner",
    "RUNNERS",
]
