# Meal Analysis Prompt Experiment History

## Summary Table

| Run | Version | F1 | Precision | Recall | State Acc | Change from Baseline |
|-----|---------|-----|-----------|--------|-----------|---------------------|
| 1 | v1_baseline | 0.429 | 0.616 | 0.353 | 0.158 | — |
| 2 | v2_recall_focus | 0.483 | 0.541 | 0.465 | 0.122 | F1 +12.6%, R +31.7% |
| 3 | v3_recipe_inference | **0.522** | 0.582 | **0.514** | 0.166 | **F1 +21.7%, R +45.7%** |

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

---

## Learnings

1. **Ground truth alignment matters**: The BBC Good Food ground truth includes recipe ingredients (onion, garlic, flour, stock) that aren't visually visible. Prompting for "visible ingredients only" misses these.

2. **Recipe inference is effective**: Telling the model to infer typical recipe ingredients based on dish type dramatically improves alignment with ground truth.

3. **Precision/recall trade-off is manageable**: Recipe inference improved both F1 and precision vs v2, while maintaining recall gains.

4. **State accuracy is hard**: All experiments show ~15% state accuracy. This may need dedicated prompt engineering or different approach.

---

## Next Experiments to Try

- **v4_state_focused**: Focus on improving state detection with visual cues
- **v5_combined**: Combine v3's recipe inference with more explicit state guidance
- **v6_few_shot**: Add more specific few-shot examples for common dishes
