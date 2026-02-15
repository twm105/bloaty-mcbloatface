"""Meal analysis evaluation runner."""

import json

from .base import BaseEvalRunner
from evals.metrics import score_meal_analysis, score_meal_analysis_soft, aggregate_meal_analysis_scores


class MealAnalysisRunner(BaseEvalRunner):
    """Evaluate meal image analysis accuracy.

    Tests the analyze_meal_image() AI service method against
    ground truth ingredient lists scraped from recipe sites.
    """

    def load_dataset(self) -> list[dict]:
        """Load test cases from ground truth file.

        Returns:
            List of test case dicts
        """
        gt_path = self.config.dataset_path / "ground_truth" / "meal_analysis.json"

        if not gt_path.exists():
            raise FileNotFoundError(
                f"Ground truth file not found: {gt_path}\n"
                f"Run scrapers first: python -m evals.run scrape --source bbc_good_food"
            )

        with open(gt_path) as f:
            data = json.load(f)

        return data.get("test_cases", [])

    async def evaluate_single(self, test_case: dict) -> dict:
        """Run evaluation on a single meal image.

        Args:
            test_case: Dict with 'id', 'image_path', 'expected'

        Returns:
            Dict with prediction, expected, and score
        """
        # Resolve image path relative to dataset directory
        image_path = self.config.dataset_path / test_case["image_path"]

        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        # Check cache first
        f"meal_analysis_{test_case['id']}_{self.config.model}"
        cached_result = None

        if self.cache_manager:
            cached_result = self.cache_manager.get(
                "analyze_meal_image",
                image_path=str(image_path),
                model=self.config.model,
            )

        if cached_result:
            predicted = cached_result
        else:
            # Call AI service
            predicted = await self.ai_service.analyze_meal_image(
                image_path=str(image_path),
                user_notes=test_case.get("user_notes"),
            )

            # Cache the result
            if self.cache_manager:
                self.cache_manager.set(
                    "analyze_meal_image",
                    predicted,
                    image_path=str(image_path),
                    model=self.config.model,
                )

        # Score the result
        expected = test_case["expected"]

        # Use LLM judge for soft scoring if enabled
        if self.config.use_llm_judge:
            score = await score_meal_analysis_soft(
                predicted,
                expected,
                claude_service=self.ai_service,
                cache_manager=self.cache_manager,
                verbose=self.config.verbose,
            )
        else:
            score = score_meal_analysis(predicted, expected)

        return {
            "id": test_case["id"],
            "source": test_case.get("source"),
            "image_path": str(test_case["image_path"]),
            "predicted": {
                "meal_name": predicted.get("meal_name"),
                "ingredients": predicted.get("ingredients", []),
            },
            "expected": expected,
            "score": {
                "precision": score.precision,
                "recall": score.recall,
                "f1": score.f1,
                "state_accuracy": score.state_accuracy,
                "meal_name_similarity": score.meal_name_similarity,
            },
            "ingredient_details": score.ingredient_details,
        }

    def compute_aggregate_metrics(self, results: list[dict]) -> dict:
        """Compute aggregate metrics from individual results.

        Args:
            results: List of result dicts from evaluate_single()

        Returns:
            Aggregate metrics with mean, min, max for each metric
        """
        return aggregate_meal_analysis_scores(results)
