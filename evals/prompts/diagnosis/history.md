# Diagnosis Root Cause Classification - Experiment Log

## Experiment History

| Run | Prompt | Medical Context | Accuracy | Precision | Recall | F1 | Discard Acc | Keep Acc | Notes |
|-----|--------|----------------|----------|-----------|--------|-----|-------------|----------|-------|
| 5 | v1_baseline | None (no web search) | 0.927 | 0.864 | 1.000 | 0.927 | 0.864 | 1.000 | Baseline: v2 harder dataset, 41 cases. 3 failures in gap_food_discard. |
| 7 | v2_with_research | Dataset medical_context | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | Pipeline reorder: medical context fixes all 3 gap food failures. |

## Analysis

### Run 7 — v2_with_research (medical context from dataset)
- **41/41 correct** (22/22 discard, 19/19 keep)
- **All 3 previously failing gap foods now correctly discarded**:
  - **coconut oil**: Now correctly DISCARDED. Medical context states "no FODMAPs, no allergens, well-tolerated."
  - **oats**: Now correctly DISCARDED. Medical context states "gluten-free, low-FODMAP in standard portions."
  - **maple syrup**: Now correctly DISCARDED. Medical context states "recommended low-FODMAP sweetener."
- **Key insight**: The v2 prompt removes hardcoded DISCARD/KEEP lists in favor of evidence-based reasoning from the medical context. The model correctly defers to the medical research for foods it would otherwise be uncertain about.
- **No regressions**: All listed triggers, gap keeps, adversarial stats, and weak stats triggers remain 100%.

### Per-Category Breakdown (Run 7)
| Category | Accuracy | Correct/Total |
|----------|----------|---------------|
| listed_with_confounders | 100% | 5/5 |
| listed_no_confounders | 100% | 3/3 |
| gap_food_discard | 100% | 7/7 |
| adversarial_stats | 100% | 7/7 |
| listed_trigger | 100% | 8/8 |
| gap_food_keep | 100% | 7/7 |
| weak_stats_trigger | 100% | 4/4 |

---

### Run 5 — Baseline (v1_baseline, no medical context, v2 dataset)
- **38/41 correct** (19/22 discard, 19/19 keep)
- **3 false positives** — all in `gap_food_discard` category (safe foods not in prompt's DISCARD list):
  - **coconut oil**: KEPT (should discard). Not in either list, no confounders. Model lacks medical knowledge that refined coconut oil is pure fat with no FODMAPs.
  - **oats**: KEPT (should discard). Not in either list. Model likely confused oats with wheat/grains (wheat IS in the KEEP list). Oats are actually low-FODMAP and safe.
  - **maple syrup**: KEPT (should discard). Not in either list, no confounders. Model doesn't know maple syrup is the recommended low-FODMAP sweetener.
- **Pattern**: The prompt's "DEFAULT TO DISCARD" instruction fails for gap foods that the model has some vague concern about. Without explicit medical research, the model errs toward keeping anything it's uncertain about.
- **All gap KEEP foods (mushrooms, honey, apple, etc.) scored 100%** — the model's general medical knowledge is sufficient to identify unlisted triggers.
- **Adversarial stats scored 100%** — the explicit DISCARD list overrides even very strong stats for listed foods.

### Per-Category Breakdown (Run 5)
| Category | Accuracy | Correct/Total |
|----------|----------|---------------|
| listed_with_confounders | 100% | 5/5 |
| listed_no_confounders | 100% | 3/3 |
| gap_food_discard | 57% | 4/7 |
| adversarial_stats | 100% | 7/7 |
| listed_trigger | 100% | 8/8 |
| gap_food_keep | 100% | 7/7 |
| weak_stats_trigger | 100% | 4/4 |

## Conclusion

The pipeline reorder (research_ingredient → classify_root_cause → adapt_to_plain_english) eliminates the gap food problem by providing expert medical context before classification. The v2 prompt's evidence-based approach is strictly superior to v1's hardcoded list approach.

**Production recommendation**: Use v2_with_research prompt with the reordered pipeline. Update `CURRENT_VERSION` when deploying.
