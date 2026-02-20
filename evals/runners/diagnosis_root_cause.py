"""Diagnosis root cause classification evaluation runner."""

import json

from .base import BaseEvalRunner
from evals.metrics import (
    score_root_cause_classification,
    aggregate_root_cause_scores,
)


class DiagnosisRootCauseRunner(BaseEvalRunner):
    """Evaluate root cause classification accuracy.

    Tests the classify_root_cause() AI service method against
    ground truth keep/discard decisions for ingredients.

    Supports two modes:
    - Default (web_search=False): fast, deterministic, cheap. Tests prompt
      reasoning without web search noise.
    - Realistic (--web-search): matches production flow. The model can search
      the web, which introduces noise and conflicting info. Expensive and slow.
    """

    def load_dataset(self) -> list[dict]:
        """Load test cases from ground truth file.

        Returns:
            List of test case dicts
        """
        gt_path = (
            self.config.dataset_path / "ground_truth" / "diagnosis_root_cause.json"
        )

        if not gt_path.exists():
            raise FileNotFoundError(f"Ground truth file not found: {gt_path}")

        with open(gt_path) as f:
            data = json.load(f)

        return data.get("test_cases", [])

    async def evaluate_single(self, test_case: dict) -> dict:
        """Run evaluation on a single test case.

        Args:
            test_case: Dict with 'id', 'ingredient_data', 'cooccurrence_data',
                       'medical_context', 'expected'

        Returns:
            Dict with prediction, expected, and score
        """
        ingredient_data = test_case["ingredient_data"]
        cooccurrence_data = test_case.get("cooccurrence_data", [])
        expected = test_case["expected"]
        prompt_version = self.config.prompt_version
        web_search = self.config.web_search

        # Cache key includes web_search to avoid mixing cached results
        cache_key_parts = {
            "ingredient_name": ingredient_data["ingredient_name"],
            "model": self.config.model,
            "prompt_version": prompt_version,
            "web_search": str(web_search),
        }

        # Check cache
        cached_result = None
        if self.cache_manager:
            cached_result = self.cache_manager.get(
                "classify_root_cause",
                **cache_key_parts,
            )

        if cached_result:
            predicted = cached_result
        else:
            # For baseline (Phase A): pass empty medical_grounding
            # For reordered pipeline (Phase B): pass medical_context from dataset
            medical_grounding = ""
            if prompt_version not in ("current", "v1_baseline"):
                # Non-baseline versions get medical context from dataset
                medical_grounding = test_case.get("medical_context", "")

            if prompt_version not in ("current", "v1_baseline"):
                # Use versioned prompt
                predicted = await self._classify_with_versioned_prompt(
                    ingredient_data=ingredient_data,
                    cooccurrence_data=cooccurrence_data,
                    medical_grounding=medical_grounding,
                    prompt_version=prompt_version,
                    web_search_enabled=web_search,
                )
            else:
                # Use default AI service method
                predicted = await self.ai_service.classify_root_cause(
                    ingredient_data=ingredient_data,
                    cooccurrence_data=cooccurrence_data,
                    medical_grounding="",
                    web_search_enabled=web_search,
                )

            # Cache the result
            if self.cache_manager:
                self.cache_manager.set(
                    "classify_root_cause",
                    predicted,
                    **cache_key_parts,
                )

        # Score the result
        score = score_root_cause_classification(predicted, expected)

        return {
            "id": test_case["id"],
            "category": test_case.get("category"),
            "ingredient": ingredient_data["ingredient_name"],
            "predicted": {
                "root_cause": predicted.get("root_cause"),
                "discard_justification": predicted.get("discard_justification"),
                "confounded_by": predicted.get("confounded_by"),
                "medical_reasoning": predicted.get("medical_reasoning"),
            },
            "expected": expected,
            "score": {
                "correct": score.correct,
                "predicted": score.predicted,
                "expected": score.expected,
                "confounder_mentioned": score.confounder_mentioned,
            },
        }

    async def _classify_with_versioned_prompt(
        self,
        ingredient_data: dict,
        cooccurrence_data: list,
        medical_grounding: str,
        prompt_version: str,
        web_search_enabled: bool = False,
    ) -> dict:
        """Classify root cause with a specific prompt version.

        Args:
            ingredient_data: Dict with ingredient stats
            cooccurrence_data: List of co-occurrence records
            medical_grounding: Medical context string
            prompt_version: Prompt version name
            web_search_enabled: Whether to enable web search tool

        Returns:
            Parsed classification result dict
        """
        from evals.prompts.diagnosis import get_prompt
        from app.services.ai_schemas import RootCauseSchema

        # Load the versioned prompt
        system_prompt = get_prompt(prompt_version)

        # Reuse the same formatting logic from ai_service
        formatted_input = self.ai_service._format_root_cause_input(
            ingredient_data, cooccurrence_data, medical_grounding
        )

        messages = [{"role": "user", "content": formatted_input}]

        request_params = {
            "model": self.ai_service.sonnet_model,
            "max_tokens": 1024,
            "stop_sequences": ["\n```", "```"],
            "system": [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
        }

        # Add web search tool if enabled and no medical grounding provided
        if web_search_enabled and not medical_grounding:
            request_params["tools"] = [
                {"type": "web_search_20250305", "name": "web_search"}
            ]

        validated, _raw_text, _response = self.ai_service._call_with_schema_retry(
            messages=messages,
            schema_class=RootCauseSchema,
            request_params=request_params,
        )

        return validated

    def _print_verbose_score(self, result: dict):
        """Print verbose score for a single root cause result."""
        score = result.get("score", {})
        correct = score.get("correct", False)
        predicted = score.get("predicted")
        expected = score.get("expected")
        category = result.get("category", "")
        status = "CORRECT" if correct else "WRONG"
        pred_label = "KEEP" if predicted else "DISCARD"
        exp_label = "KEEP" if expected else "DISCARD"
        confounder = (
            " (confounder mentioned)" if score.get("confounder_mentioned") else ""
        )
        cat_tag = f" [{category}]" if category else ""
        print(
            f"    {status}: predicted={pred_label}, expected={exp_label}"
            f"{confounder}{cat_tag}"
        )

    def compute_aggregate_metrics(self, results: list[dict]) -> dict:
        """Compute aggregate metrics from individual results.

        Also computes per-category breakdown for analysis.

        Args:
            results: List of result dicts from evaluate_single()

        Returns:
            Aggregate metrics dict with overall + per-category breakdown
        """
        overall = aggregate_root_cause_scores(results)

        # Per-category breakdown
        categories = {}
        for r in results:
            cat = r.get("category", "unknown")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(r)

        category_breakdown = {}
        for cat, cat_results in categories.items():
            cat_scores = aggregate_root_cause_scores(cat_results)
            category_breakdown[cat] = {
                "accuracy": cat_scores.get("accuracy", 0),
                "total": cat_scores.get("total_cases", 0),
                "correct": sum(
                    1 for r in cat_results if r.get("score", {}).get("correct")
                ),
            }

        overall["category_breakdown"] = category_breakdown
        return overall
