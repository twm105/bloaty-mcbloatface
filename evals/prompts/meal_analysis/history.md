# Meal Analysis Prompt Experiment History

## Summary Table

| Run | Version | F1 | Precision | Recall | State Acc | Change from Baseline |
|-----|---------|-----|-----------|--------|-----------|---------------------|
| 1 | v1_baseline | 0.429 | 0.616 | 0.353 | 0.158 | — |
| 2 | v2_recall_focus | 0.483 | 0.541 | 0.465 | 0.122 | F1 +12.6%, R +31.7% |
| 3 | v3_recipe_inference | 0.522 | 0.582 | 0.514 | 0.166 | F1 +21.7%, R +45.7% |
| 8 | v3_recipe_inference | 0.528 | 0.587 | 0.520 | 0.162 | (re-baseline for v4 comparison) |
| 9 | v4_atomic_ingredients | **0.550** | 0.594 | **0.538** | 0.162 | **F1 +28.2%, R +52.4%** |

---

## Baseline (2026-02-15)

**Run ID 1** - v1_baseline
- F1: 0.429
- Precision: 0.616
- Recall: 0.353
- State Accuracy: 0.158
- Samples: 20

**Key Issues Identified:**
- Low recall (35%): Many ground truth ingredients not detected
- Missing: spices, seasonings, cooking oils, aromatics
- Ground truth includes recipe ingredients, not just visible ingredients
- State accuracy poor (16%)

---

## Experiments

### v2_recall_focus (Run ID 2)
**Hypothesis:** Explicit "err on inclusion" instruction will improve recall
**Changes:**
- Added "ERR ON THE SIDE OF INCLUSION" instruction
- Added explicit list of commonly missed ingredients (cooking fats, aromatics, seasonings)
- Reduced confidence threshold guidance

**Results:**
- F1: 0.483 (+0.054, +12.6%)
- Precision: 0.541 (-0.075, -12.2%)
- Recall: 0.465 (+0.112, +31.7%)
- State Accuracy: 0.122 (-0.036)

**Analysis:** Hypothesis validated. Recall improved significantly as expected. Precision dropped as predicted. Net F1 gain of +12.6%.

### v3_recipe_inference (Run ID 3) ⭐ BEST
**Hypothesis:** Instructing model to infer typical recipe ingredients will match ground truth better
**Changes:**
- Added instruction to include both VISIBLE and TYPICAL ingredients
- Added recipe inference guidelines based on dish type
- Added specific examples for common dishes (cottage pie, Thai green curry, Caesar salad)

**Results:**
- F1: 0.522 (+0.093, +21.7%) ⭐
- Precision: 0.582 (-0.034, -5.5%)
- Recall: 0.514 (+0.161, +45.7%) ⭐
- State Accuracy: 0.166 (+0.008)

**Analysis:** Best performing prompt. Recipe inference approach correctly captures that ground truth includes recipe ingredients, not just photographically visible ones. Precision recovered compared to v2 while recall improved further.

### v4_atomic_ingredients (Run ID 9) ⭐ BEST
**Hypothesis:** Decomposing compound ingredients (sauces, pastes, stocks, dressings, dish names) into atomic base ingredients improves correlation utility for the diagnosis pipeline.
**Changes:**
- Added INGREDIENT ATOMICITY section: "elements, not compounds"
- Decomposition rules for sauces, pastes, stocks, dressings, dish names
- Keep-as-is rules for staples (bread, pasta, cheese, tofu, etc.)
- Updated inference examples to use atomic ingredients (no more "Worcestershire sauce", "green curry paste", "Caesar dressing")
- Updated worked example (cottage pie) with atomic ingredients
- Updated JSON example (spaghetti bolognese) with garlic, tomato, olive oil, carrot, celery
- New confidence tier: 0.4-0.6 for decomposed sub-ingredients

**Re-baseline (Run ID 8)** — v3 re-run for fair comparison:
- F1: 0.528 | Precision: 0.587 | Recall: 0.520 | State Accuracy: 0.162

**Results (Run ID 9):**
- F1: 0.550 (+0.022 vs re-baseline, +4.2%)
- Precision: 0.594 (+0.007, +1.2%)
- Recall: 0.538 (+0.018, +3.5%)
- State Accuracy: 0.162 (unchanged)

**Analysis:** Modest F1 improvement (+4.2%) despite ground truth still using compound ingredients. The LLM judge gives partial credit (e.g., "anchovies" gets 0.5 against "Worcestershire sauce"). The real value is qualitative: atomic ingredients are far more useful for the diagnosis correlation pipeline. A user reacting to "green curry paste" tells us nothing; knowing the sub-ingredients (lemongrass, galangal, chili) enables proper trigger identification.

**Decision:** Promote to production. The atomic format is objectively better for the app's core purpose (symptom-trigger correlation), and eval scores improved slightly even against a compound ground truth that disadvantages this approach.

---

## Learnings

1. **Ground truth alignment matters**: The BBC Good Food ground truth includes recipe ingredients (onion, garlic, flour, stock) that aren't visually visible. Prompting for "visible ingredients only" misses these.

2. **Recipe inference is effective**: Telling the model to infer typical recipe ingredients based on dish type dramatically improves alignment with ground truth.

3. **Precision/recall trade-off is manageable**: Recipe inference improved both F1 and precision vs v2, while maintaining recall gains.

4. **State accuracy is hard**: All experiments show ~15% state accuracy. This may need dedicated prompt engineering or different approach.

5. **Atomic ingredients improve downstream utility**: Even when eval scores don't dramatically change (ground truth uses compounds), decomposing sauces/pastes/stocks into base ingredients is critical for the diagnosis pipeline. LLM judge partially compensates by giving 0.5 scores for sub-ingredient matches.

---

## Next Experiments to Try

- **Ground truth migration**: Convert ground truth to atomic format — current scores undercount v4's real accuracy
- **v5_state_focused**: Focus on improving state detection with visual cues (state accuracy stuck at ~16%)
- **v6_combined**: Combine v4's atomicity with more explicit state guidance
- **v7_few_shot**: Add more specific few-shot examples for common dishes
