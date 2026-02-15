"""Meal analysis evaluation runner."""

import base64
import json
from pathlib import Path

from .base import BaseEvalRunner
from evals.metrics import (
    score_meal_analysis,
    score_meal_analysis_soft,
    aggregate_meal_analysis_scores,
)


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

        # Check cache first (include prompt_version in cache key)
        cached_result = None
        prompt_version = self.config.prompt_version

        if self.cache_manager:
            cached_result = self.cache_manager.get(
                "analyze_meal_image",
                image_path=str(image_path),
                model=self.config.model,
                prompt_version=prompt_version,
            )

        if cached_result:
            predicted = cached_result
        else:
            # Load prompt for this version
            if prompt_version != "current":
                predicted = await self._analyze_with_versioned_prompt(
                    image_path=str(image_path),
                    prompt_version=prompt_version,
                    user_notes=test_case.get("user_notes"),
                )
            else:
                # Use default AI service method
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
                    prompt_version=prompt_version,
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

    async def _analyze_with_versioned_prompt(
        self,
        image_path: str,
        prompt_version: str,
        user_notes: str = None,
    ) -> dict:
        """Analyze meal image with a specific prompt version.

        Args:
            image_path: Path to meal image
            prompt_version: Prompt version name (e.g., "v2_recall_focus")
            user_notes: Optional user context

        Returns:
            Parsed meal analysis result dict
        """
        from evals.prompts.meal_analysis import get_prompt

        # Load the versioned prompt
        system_prompt = get_prompt(prompt_version)

        # Read and encode image
        with open(image_path, "rb") as f:
            image_data = base64.standard_b64encode(f.read()).decode("utf-8")

        suffix = Path(image_path).suffix.lower()
        media_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        media_type = media_types.get(suffix, "image/jpeg")

        # Build user message
        user_message = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": image_data,
                },
            },
            {
                "type": "text",
                "text": "Analyze this meal and identify all visible ingredients.",
            },
        ]

        if user_notes:
            user_message.append({"type": "text", "text": f"User notes: {user_notes}"})

        # Call Claude API directly
        response = self.ai_service.client.messages.create(
            model=self.ai_service.haiku_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": user_message}],
            system=system_prompt,
        )

        raw_response = response.content[0].text

        # Parse JSON response
        try:
            if "```json" in raw_response or "```" in raw_response:
                json_str = raw_response
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1]
                elif "```" in json_str:
                    json_str = json_str.split("```")[1]
                json_str = json_str.split("```")[0].strip()
                parsed = json.loads(json_str)
            else:
                parsed = json.loads(raw_response)

            return {
                "meal_name": parsed.get("meal_name", "Untitled Meal"),
                "ingredients": parsed.get("ingredients", []),
                "raw_response": raw_response,
                "model": self.ai_service.haiku_model,
            }
        except json.JSONDecodeError as e:
            raise ValueError(f"Could not parse AI response as JSON: {str(e)}")

    def compute_aggregate_metrics(self, results: list[dict]) -> dict:
        """Compute aggregate metrics from individual results.

        Args:
            results: List of result dicts from evaluate_single()

        Returns:
            Aggregate metrics with mean, min, max for each metric
        """
        return aggregate_meal_analysis_scores(results)
