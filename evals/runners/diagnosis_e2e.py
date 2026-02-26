"""End-to-end diagnosis pipeline evaluation runner."""

import json

from .base import BaseEvalRunner
from evals.metrics import (
    score_e2e_scenario,
    aggregate_e2e_scores,
)


class DiagnosisE2ERunner(BaseEvalRunner):
    """Evaluate the full diagnosis pipeline end-to-end.

    For each scenario with multiple ingredients:
    1. Classify each ingredient (keep/discard) via classify_root_cause()
    2. For kept ingredients, generate plain English via adapt_to_plain_english()
    3. Score keep/discard decisions against ground truth
    4. Optionally score reasoning quality via LLM-as-judge

    Supports two modes:
    - Default (web_search=False): uses pre-baked medical_context from dataset.
      Skips research_ingredient(). Fast and cheap (~$0.10 for 10 scenarios).
    - Realistic (--web-search): calls research_ingredient() live.
      Matches production flow. Expensive (~$2.50 for 10 scenarios).
    """

    def load_dataset(self) -> list[dict]:
        """Load E2E scenarios from ground truth file."""
        gt_path = self.config.dataset_path / "ground_truth" / "diagnosis_e2e.json"

        if not gt_path.exists():
            raise FileNotFoundError(f"Ground truth file not found: {gt_path}")

        with open(gt_path) as f:
            data = json.load(f)

        return data.get("scenarios", [])

    async def evaluate_single(self, test_case: dict) -> dict:
        """Run the full pipeline on a single scenario.

        For each ingredient_to_analyze:
        1. Call classify_root_cause() with ingredient data + cooccurrence + medical context
        2. If kept (root_cause=True), call adapt_to_plain_english()
        3. Collect all results for scoring

        Args:
            test_case: Scenario dict with ingredients_to_analyze, ground_truth, etc.

        Returns:
            Dict with per-ingredient predictions and scenario-level score
        """
        ingredients = test_case["ingredients_to_analyze"]
        ground_truth = test_case["ground_truth"]
        web_search = self.config.web_search

        ingredient_results = []
        total_usage = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}

        for ing in ingredients:
            # Build ingredient_data in the format classify_root_cause expects
            ingredient_data = {
                "ingredient_name": ing["ingredient_name"],
                "times_eaten": ing["times_eaten"],
                "total_symptom_occurrences": ing["total_symptom_occurrences"],
                "confidence_level": ing["confidence_level"],
                "associated_symptoms": ing["associated_symptoms"],
            }

            # Build cooccurrence_data
            cooccurrence_data = [
                {
                    "with_ingredient_name": co["with_ingredient_name"],
                    "cooccurrence_meals": co["cooccurrence_meals"],
                    "conditional_probability": co["conditional_probability"],
                }
                for co in ing.get("cooccurrence", [])
            ]

            # Medical grounding: use pre-baked context unless web search is enabled
            medical_grounding = ""
            if not web_search:
                medical_grounding = ing.get("medical_context", "")

            # Cache key
            cache_key_parts = {
                "scenario": test_case["id"],
                "ingredient_name": ing["ingredient_name"],
                "model": self.config.model,
                "web_search": str(web_search),
            }

            # Check cache for classify result
            cached_classify = None
            if self.cache_manager:
                cached_classify = self.cache_manager.get(
                    "e2e_classify_root_cause",
                    **cache_key_parts,
                )

            if cached_classify:
                classify_result = cached_classify
            else:
                classify_result = await self.ai_service.classify_root_cause(
                    ingredient_data=ingredient_data,
                    cooccurrence_data=cooccurrence_data,
                    medical_grounding=medical_grounding,
                    web_search_enabled=web_search,
                )

                if self.cache_manager:
                    self.cache_manager.set(
                        "e2e_classify_root_cause",
                        classify_result,
                        **cache_key_parts,
                    )

            # Track usage
            usage = classify_result.get("usage_stats", {})
            for key in total_usage:
                total_usage[key] += usage.get(key, 0)

            # Build result for this ingredient
            ing_result = {
                "ingredient_name": ing["ingredient_name"],
                "root_cause": classify_result.get("root_cause", False),
                "confidence_level": ing["confidence_level"],
                "discard_justification": classify_result.get("discard_justification"),
                "confounded_by": classify_result.get("confounded_by"),
                "medical_reasoning": classify_result.get("medical_reasoning"),
            }

            # For kept ingredients, run adapt_to_plain_english
            if classify_result.get("root_cause", False):
                plain_english = await self._run_adapt_to_plain_english(
                    test_case, ing, web_search, cache_key_parts
                )
                if plain_english:
                    ing_result["diagnosis_summary"] = plain_english.get(
                        "diagnosis_summary", ""
                    )
                    ing_result["recommendations_summary"] = plain_english.get(
                        "recommendations_summary", ""
                    )
                    pe_usage = plain_english.get("usage_stats", {})
                    for key in total_usage:
                        total_usage[key] += pe_usage.get(key, 0)

            ingredient_results.append(ing_result)

        # Score scenario
        scenario_score = score_e2e_scenario(ingredient_results, ground_truth)

        # Run LLM judge if enabled
        judge_scores = {}
        if self.config.use_llm_judge:
            judge_scores = await self._run_llm_judges(
                test_case, ingredient_results, ground_truth
            )

        return {
            "id": test_case["id"],
            "name": test_case["name"],
            "ingredient_results": ingredient_results,
            "score": {
                "trigger_precision": scenario_score.trigger_precision,
                "trigger_recall": scenario_score.trigger_recall,
                "trigger_f1": scenario_score.trigger_f1,
                "bystander_precision": scenario_score.bystander_precision,
                "bystander_recall": scenario_score.bystander_recall,
                "bystander_f1": scenario_score.bystander_f1,
                "no_false_alarm": scenario_score.no_false_alarm,
                "details": scenario_score.details,
            },
            "judge_scores": judge_scores,
            "ground_truth": ground_truth,
            "usage_stats": total_usage,
        }

    async def _run_adapt_to_plain_english(
        self,
        test_case: dict,
        ingredient: dict,
        web_search: bool,
        cache_key_parts: dict,
    ) -> dict | None:
        """Run adapt_to_plain_english for a kept ingredient.

        Constructs the medical_research dict from the ingredient's medical_context
        (when not using web search) and uses the timeline meals as meal history.
        """
        # Check cache
        pe_cache_key = {**cache_key_parts, "step": "adapt_plain_english"}
        if self.cache_manager:
            cached = self.cache_manager.get("e2e_adapt_plain_english", **pe_cache_key)
            if cached:
                return cached

        # Build ingredient_data
        ingredient_data = {
            "ingredient_name": ingredient["ingredient_name"],
            "times_eaten": ingredient["times_eaten"],
            "total_symptom_occurrences": ingredient["total_symptom_occurrences"],
            "confidence_level": ingredient["confidence_level"],
            "associated_symptoms": ingredient["associated_symptoms"],
        }

        # Build medical_research from pre-baked context or live research
        if web_search:
            try:
                medical_research = await self.ai_service.research_ingredient(
                    ingredient_data=ingredient_data,
                    web_search_enabled=True,
                )
            except Exception:
                # Fallback to pre-baked context
                medical_research = {
                    "medical_assessment": ingredient.get("medical_context", ""),
                    "known_trigger_categories": [],
                    "risk_level": "high_risk",
                    "citations": [],
                }
        else:
            medical_research = {
                "medical_assessment": ingredient.get("medical_context", ""),
                "known_trigger_categories": [],
                "risk_level": "high_risk",
                "citations": [],
            }

        # Build meal history from timeline
        meal_history = []
        timeline = test_case.get("timeline", {})
        for meal in timeline.get("meals", [])[:10]:  # Limit to recent 10
            meal_history.append(
                {
                    "meal_name": meal.get("name", ""),
                    "ingredients": [ing["name"] for ing in meal.get("ingredients", [])],
                }
            )

        try:
            result = await self.ai_service.adapt_to_plain_english(
                ingredient_data=ingredient_data,
                medical_research=medical_research,
                user_meal_history=meal_history,
            )

            if self.cache_manager:
                self.cache_manager.set(
                    "e2e_adapt_plain_english", result, **pe_cache_key
                )

            return result
        except Exception as e:
            if self.config.verbose:
                print(f"      adapt_to_plain_english failed: {e}")
            return None

    async def _run_llm_judges(
        self,
        test_case: dict,
        ingredient_results: list[dict],
        ground_truth: dict,
    ) -> dict:
        """Run LLM-as-judge scoring on kept ingredients.

        Scores cross-referencing, medical accuracy, plain English, and
        appropriate uncertainty for each kept ingredient, then averages.
        """
        from evals.judge_prompts import (
            CROSS_REFERENCING_JUDGE_PROMPT,
            MEDICAL_ACCURACY_JUDGE_PROMPT,
            PLAIN_ENGLISH_JUDGE_PROMPT,
            APPROPRIATE_UNCERTAINTY_JUDGE_PROMPT,
        )

        kept_results = [r for r in ingredient_results if r.get("root_cause")]
        if not kept_results:
            return {}

        all_scores = {
            "cross_referencing": [],
            "medical_accuracy": [],
            "plain_english": [],
            "appropriate_uncertainty": [],
        }

        for result in kept_results:
            ing_name = result["ingredient_name"]
            diagnosis = result.get("diagnosis_summary", "")
            recommendations = result.get("recommendations_summary", "")

            if not diagnosis:
                continue

            # Find the ingredient's medical context
            medical_context = ""
            for ing in test_case["ingredients_to_analyze"]:
                if ing["ingredient_name"] == ing_name:
                    medical_context = ing.get("medical_context", "")
                    break

            decision = "KEEP (identified as trigger)"

            # Cross-referencing judge
            cross_ref_score = await self._call_judge(
                CROSS_REFERENCING_JUDGE_PROMPT.format(
                    scenario_description=test_case["description"],
                    triggers=", ".join(ground_truth["triggers"]) or "none",
                    bystanders=", ".join(ground_truth["bystanders"]) or "none",
                    key_evidence="\n".join(
                        f"- {e}" for e in ground_truth["key_evidence"]
                    ),
                    ingredient_name=ing_name,
                    decision=decision,
                    diagnosis_summary=diagnosis,
                    recommendations_summary=recommendations,
                ),
                cache_key=f"judge_cross_ref_{test_case['id']}_{ing_name}",
            )
            all_scores["cross_referencing"].append(cross_ref_score)

            # Medical accuracy judge
            med_score = await self._call_judge(
                MEDICAL_ACCURACY_JUDGE_PROMPT.format(
                    ingredient_name=ing_name,
                    medical_context=medical_context,
                    diagnosis_summary=diagnosis,
                    recommendations_summary=recommendations,
                ),
                cache_key=f"judge_med_{test_case['id']}_{ing_name}",
            )
            all_scores["medical_accuracy"].append(med_score)

            # Plain English judge
            pe_score = await self._call_judge(
                PLAIN_ENGLISH_JUDGE_PROMPT.format(
                    ingredient_name=ing_name,
                    diagnosis_summary=diagnosis,
                    recommendations_summary=recommendations,
                ),
                cache_key=f"judge_pe_{test_case['id']}_{ing_name}",
            )
            all_scores["plain_english"].append(pe_score)

            # Appropriate uncertainty judge
            evidence_summary = (
                f"{result.get('confidence_level', 'unknown')} confidence. "
                f"Mentioned in medical reasoning: "
                f"{result.get('medical_reasoning', 'N/A')[:200]}"
            )
            uncertainty_score = await self._call_judge(
                APPROPRIATE_UNCERTAINTY_JUDGE_PROMPT.format(
                    ingredient_name=ing_name,
                    confidence_level=result.get("confidence_level", "unknown"),
                    evidence_summary=evidence_summary,
                    decision=decision,
                    diagnosis_summary=diagnosis,
                ),
                cache_key=f"judge_uncertainty_{test_case['id']}_{ing_name}",
            )
            all_scores["appropriate_uncertainty"].append(uncertainty_score)

        # Average scores per dimension
        averaged = {}
        for dimension, values in all_scores.items():
            valid = [v for v in values if v is not None]
            if valid:
                averaged[dimension] = sum(valid) / len(valid)

        return averaged

    async def _call_judge(self, prompt: str, cache_key: str) -> float | None:
        """Call Haiku as LLM judge and return the score."""
        # Check cache
        if self.cache_manager:
            cached = self.cache_manager.get("e2e_llm_judge", key=cache_key)
            if cached is not None:
                return cached.get("score")

        try:
            response = self.ai_service.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )

            raw = response.content[0].text.strip()

            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                if "{" in raw and "}" in raw:
                    json_str = raw[raw.index("{") : raw.rindex("}") + 1]
                    result = json.loads(json_str)
                else:
                    return None

            score = result.get("score")
            if score not in (0.0, 0.5, 1.0, 0, 1):
                return None
            score = float(score)

            if self.cache_manager:
                self.cache_manager.set("e2e_llm_judge", {"score": score}, key=cache_key)

            return score

        except Exception:
            return None

    def _print_verbose_score(self, result: dict):
        """Print verbose score for a single E2E scenario."""
        score = result.get("score", {})
        details = score.get("details", {})

        trigger_f1 = score.get("trigger_f1", 0)
        bystander_f1 = score.get("bystander_f1", 0)

        correct_triggers = details.get("correct_triggers_kept", [])
        missed_triggers = details.get("missed_triggers", [])
        false_keeps = details.get("false_triggers_kept", [])

        status = "PERFECT" if trigger_f1 == 1.0 and bystander_f1 == 1.0 else "PARTIAL"
        if trigger_f1 == 0.0 and result.get("ground_truth", {}).get("triggers"):
            status = "FAILED"

        parts = [
            f"    {status}: trigger_F1={trigger_f1:.2f} bystander_F1={bystander_f1:.2f}"
        ]

        if correct_triggers:
            parts.append(f"      Correct triggers: {', '.join(correct_triggers)}")
        if missed_triggers:
            parts.append(f"      MISSED triggers: {', '.join(missed_triggers)}")
        if false_keeps:
            parts.append(f"      False keeps: {', '.join(false_keeps)}")

        judge = result.get("judge_scores", {})
        if judge:
            judge_strs = [f"{k}={v:.1f}" for k, v in judge.items() if v is not None]
            if judge_strs:
                parts.append(f"      Judge: {', '.join(judge_strs)}")

        print("\n".join(parts))

    def compute_aggregate_metrics(self, results: list[dict]) -> dict:
        """Compute aggregate metrics from E2E scenario results."""
        return aggregate_e2e_scores(results)
