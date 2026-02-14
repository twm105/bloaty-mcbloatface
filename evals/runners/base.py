"""Abstract base class for evaluation runners."""

import time
from abc import ABC, abstractmethod
from pathlib import Path

from evals.config import EvalConfig
from evals.results import EvalResult


class BaseEvalRunner(ABC):
    """Abstract base class for evaluation runners.

    Subclasses must implement:
    - load_dataset(): Load test cases from ground truth file
    - evaluate_single(): Run evaluation on a single test case
    - compute_aggregate_metrics(): Compute aggregate metrics from results
    """

    def __init__(self, config: EvalConfig):
        self.config = config
        self.ai_service = None  # Lazy initialization
        self.cache_manager = None

    def _init_services(self):
        """Initialize AI service and cache manager."""
        if self.ai_service is None:
            from app.services.ai_service import ClaudeService

            self.ai_service = ClaudeService()

        if self.cache_manager is None and self.config.use_cache:
            from evals.fixtures.cache_manager import CacheManager

            self.cache_manager = CacheManager(enabled=True)

    @abstractmethod
    def load_dataset(self) -> list[dict]:
        """Load test cases from ground truth file.

        Returns:
            List of test case dicts with 'id', 'image_path', 'expected', etc.
        """
        pass

    @abstractmethod
    async def evaluate_single(self, test_case: dict) -> dict:
        """Run evaluation on a single test case.

        Args:
            test_case: Dict with test case data including expected values

        Returns:
            Dict with 'id', 'predicted', 'expected', 'score', etc.
        """
        pass

    @abstractmethod
    def compute_aggregate_metrics(self, results: list[dict]) -> dict:
        """Compute aggregate metrics from individual results.

        Args:
            results: List of result dicts from evaluate_single()

        Returns:
            Dict with aggregate metrics (mean_precision, mean_recall, etc.)
        """
        pass

    async def run(self) -> EvalResult:
        """Run the full evaluation.

        Returns:
            EvalResult with all metrics, detailed results, and errors
        """
        start_time = time.time()

        # Initialize services
        self._init_services()

        # Load dataset
        test_cases = self.load_dataset()

        # Apply sample size limit
        if self.config.sample_size:
            test_cases = test_cases[: self.config.sample_size]

        if self.config.verbose:
            print(f"Running {len(test_cases)} test cases...")

        # Run evaluations
        results = []
        errors = []

        for i, case in enumerate(test_cases):
            if self.config.verbose:
                print(f"  [{i + 1}/{len(test_cases)}] {case.get('id', 'unknown')}")

            try:
                result = await self.evaluate_single(case)
                results.append(result)

                if self.config.verbose:
                    score = result.get("score", {})
                    f1 = score.get("f1", 0)
                    print(f"    F1: {f1:.3f}")

            except Exception as e:
                error_info = {"case_id": case.get("id"), "error": str(e)}
                errors.append(error_info)

                if self.config.verbose:
                    print(f"    ERROR: {e}")

        # Compute aggregate metrics
        metrics = self.compute_aggregate_metrics(results)

        execution_time = time.time() - start_time

        if self.config.verbose:
            print(f"\nCompleted in {execution_time:.2f}s")
            print(f"Results: {len(results)} success, {len(errors)} errors")

        return EvalResult(
            eval_type=self.config.eval_type,
            model=self.config.model,
            num_cases=len(test_cases),
            metrics=metrics,
            detailed_results=results,
            execution_time_seconds=execution_time,
            errors=errors,
        )
