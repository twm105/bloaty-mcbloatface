# Evals Strategy

Evaluation framework for quantifying AI feature quality and tracking performance over time.

## Overview

The evals system measures AI accuracy against ground truth datasets scraped from recipe sites. Results are stored in PostgreSQL for trend analysis across model and prompt changes.

**CLI**: `python -m evals.run`

## AI Features

| Feature | Method | Priority | Metrics | Target |
|---------|--------|----------|---------|--------|
| Meal Analysis | `analyze_meal_image()` | P1 | Ingredient P/R/F1, State Accuracy | F1 ≥0.77, State ≥0.80 |
| Meal Validation | `validate_meal_image()` | P2 | Accuracy, TPR, TNR | Acc ≥0.95 |
| Symptom Elaboration | `elaborate_symptom_tags()` | P3 | Completeness, Clinical Tone | 100% symptoms mentioned |
| Episode Detection | `detect_episode_continuation()` | P3 | Accuracy, Confidence Calibration | Acc ≥0.85 |
| Symptom Clarification | `clarify_symptom()` | P3 | Question Limit, Extraction | Max 3 questions |
| Diagnosis Confidence | `calculate_confidence()` | P1 | Level Accuracy, Distribution Spread | Accuracy ≥0.90 |
| Diagnosis Root Cause | `classify_root_cause()` | P1 | Precision, Recall, F1 | F1 ≥0.85, Recall ≥0.90 |
| Diagnosis Single Ingredient | `diagnose_single_ingredient()` | P1 | Readability, Relevance, Ethics | Readability ≥0.80 |
| Diagnosis Correlations | `diagnose_correlations()` | P2 | Relevance, Ethics, Citation Quality | Relevance ≥0.80 |
| Diagnosis E2E | Full pipeline | P2 | Kept/Discarded P/R, Plain English | Kept Recall ≥0.90 |

## Dataset

**Target**: 100 meal images with ground truth ingredients

| Source | Count | Categories |
|--------|-------|------------|
| BBC Good Food | 50 | chicken, vegetarian, seafood, salads, pasta |
| AllRecipes | 30 | quick-easy, healthy, comfort-food |
| Curated Edge Cases | 20 | poor lighting, multiple dishes, non-food negatives |

### Ground Truth Format

```json
{
  "version": "1.0",
  "test_cases": [{
    "id": "bbc_001",
    "source": "bbc_good_food",
    "image_path": "meal_images/bbc_good_food/chicken-tikka.jpg",
    "expected": {
      "meal_name": "Chicken Tikka Masala",
      "meal_name_alternatives": ["Chicken Tikka"],
      "ingredients": [{
        "name": "chicken breast",
        "name_variants": ["chicken", "chicken thigh"],
        "state": "cooked",
        "required": true
      }]
    },
    "difficulty": "medium"
  }]
}
```

### Ingredient Matching

Fuzzy matching with normalization:
- Lowercase, strip whitespace
- Remove qualifiers: "fresh", "dried", "sliced", "chopped"
- Singularize simple plurals
- Match against primary name and variants (threshold: 0.8 similarity)

## Directory Structure

```
evals/
├── run.py                      # CLI entry point
├── config.py                   # Configuration
├── metrics.py                  # Scoring functions
├── results.py                  # Database storage
├── judge_prompts.py            # LLM-as-judge prompts
├── scrapers/
│   ├── base.py                 # Abstract scraper
│   ├── bbc_good_food.py        # BBC Good Food
│   └── allrecipes.py           # AllRecipes
├── datasets/
│   ├── meal_images/            # Images (gitignored)
│   ├── ground_truth/           # JSON truth files
│   │   ├── meal_analysis.json
│   │   ├── diagnosis_confidence.json      # 30 test vectors
│   │   ├── diagnosis_root_cause.json      # 40 cases (20 keep + 20 discard)
│   │   ├── diagnosis_correlations.json    # 15 cases
│   │   ├── diagnosis_single_ingredient.json # 20 cases
│   │   └── diagnosis_e2e.json             # 10 full-pipeline scenarios
│   └── manifest.yaml           # Metadata
├── runners/
│   ├── base.py                 # BaseEvalRunner ABC
│   ├── meal_analysis.py        # Meal analysis eval
│   ├── diagnosis_confidence.py # Deterministic scoring eval
│   ├── diagnosis_root_cause.py # Root cause classification eval
│   ├── diagnosis_correlations.py # Medical analysis quality eval
│   ├── diagnosis_single_ingredient.py # Plain English quality eval
│   └── diagnosis_e2e.py        # Full pipeline integration eval
├── prompts/
│   ├── meal_analysis/          # Meal analysis prompt versions
│   └── diagnosis/              # Diagnosis prompt versions
└── fixtures/
    ├── api_cache/              # Cached responses (gitignored)
    └── cache_manager.py        # Cache logic
```

## CLI Usage

```bash
# Run evaluation
python -m evals.run eval --eval-type meal_analysis
python -m evals.run eval --eval-type meal_analysis --sample 10 --verbose
python -m evals.run eval --eval-type meal_analysis --no-cache  # Fresh API calls

# Scrape recipes
python -m evals.run scrape --source bbc_good_food --limit 50 --download-images
python -m evals.run scrape --source allrecipes --category healthy --limit 30

# View history
python -m evals.run history --eval-type meal_analysis --limit 10

# Compare runs
python -m evals.run compare --runs 1,2,3

# Run with specific prompt version (for experiments)
python -m evals.run eval --eval-type meal_analysis --prompt-version v2_recall_focus \
  --notes "HYPOTHESIS: Explicit 'list ALL' instruction improves recall"

# Disable LLM judge (use string matching only)
python -m evals.run eval --eval-type meal_analysis --no-llm-judge

# Generate HTML report
python -m scripts.generate_eval_report --run-id 3
```

## LLM-as-Judge Scoring

For ingredient matching, the evals use Haiku as an LLM judge to provide **soft scores** (0, 0.5, or 1.0) rather than binary matching. This handles semantic equivalence that string matching misses.

### Score Levels
| Score | Meaning | Example |
|-------|---------|---------|
| 1.0 | Exact or semantic match | "ground beef" ↔ "minced beef" |
| 0.5 | Partial match (subset/superset) | "cheddar cheese" ↔ "cheese" |
| 0.0 | No match | "tomato" ↔ "onion" |

### Soft Metrics
- **Soft Precision** = sum(match_scores) / num_predicted
- **Soft Recall** = sum(best_match_scores_for_required) / num_required
- **Soft F1** = harmonic mean of soft precision and recall

### Cache
LLM judge responses are cached to avoid repeated API costs. Cache key includes:
- Predicted ingredient name
- Expected ingredient list hash
- Prompt version (for experiments)

## Prompt Iteration Workflow

Iterative prompt engineering to improve AI feature accuracy.

### Structure

```
evals/prompts/
├── meal_analysis/
│   ├── __init__.py           # get_prompt(version), CURRENT_VERSION
│   ├── v1_baseline.py        # Original production prompt
│   ├── v2_recall_focus.py    # Experiment: emphasize inclusion
│   ├── v3_recipe_inference.py # Experiment: infer recipe ingredients
│   └── history.md            # Experiment log with results
```

### Version File Format

Each version documents its hypothesis:

```python
"""
Version: v2_recall_focus
Hypothesis: Explicit "list ALL visible ingredients" instruction improves recall
Expected: Recall +0.15, Precision -0.05 (acceptable trade-off)
Changes:
  - Added "ERR ON THE SIDE OF INCLUSION" instruction
  - Added commonly missed ingredients list
Created: 2026-02-15
Result: F1 +12.6%, Recall +31.7% ✓
"""
MEAL_ANALYSIS_SYSTEM_PROMPT = """..."""
```

### Workflow

1. **Hypothesize**: Identify weakness in current scores, form hypothesis
2. **Build**: Create new version file `vN_descriptive_name.py`
3. **Eval**: Run with `--prompt-version vN_name --notes "..."`
4. **Record**: Update `history.md` with results and analysis
5. **Repeat**: If target not met, form new hypothesis
6. **Promote**: If eval results are acceptable, update production prompt in `app/services/prompts.py`
   - Always eval BEFORE changing production — never update production prompts without running evals first
   - Document the promotion in history.md

### CLI Examples

```bash
# Run baseline (or any version)
docker compose exec web python -m evals.run eval \
  --eval-type meal_analysis --sample 20 \
  --prompt-version v1_baseline \
  --notes "BASELINE: Initial measurement"

# Run experiment
docker compose exec web python -m evals.run eval \
  --eval-type meal_analysis --sample 20 \
  --prompt-version v3_recipe_inference \
  --notes "HYPOTHESIS: Recipe inference matches ground truth better"

# Compare all runs
docker compose exec web python -m evals.run compare --runs 1,2,3
```

### Experiment History

See `evals/prompts/meal_analysis/history.md` for full experiment log with:
- Summary table of all runs
- Per-version hypothesis, changes, and results
- Key learnings and next experiments

**Current best (v3_recipe_inference)**: F1=0.522, Recall=0.514 (+45.7% from baseline)

## Diagnosis Evals

**Full implementation plan**: `.claude/plans/rosy-zooming-blanket.md`

The diagnosis feature has 5 eval suites covering each pipeline step ("unit evals") plus end-to-end integration. Implementation is phased — Phase 1 (confidence) costs zero API calls, subsequent phases build on each other.

### Eval 1: Confidence Scoring (Deterministic, zero API cost)
- **What**: 30 test vectors for `calculate_confidence()` covering all 4 confidence levels
- **Why**: Validates the scoring formula produces realistic spread (currently everything is "medium")
- **Scoring**: Exact level match + score range check + distribution spread across high/medium/low/insufficient
- **Targets**: level_accuracy ≥0.90, distribution_spread = 4

### Eval 2: Root Cause Classification (AI, ~$0.08)
- **What**: 40 cases — 20 should-discard (chicken, rice, carrots, etc.) + 20 should-keep (garlic, onion, dairy, allergens)
- **Why**: Directly addresses broken non-root-cause bucketing
- **Ground truth sources**: Monash FODMAP database, FDA Top 9 Allergens, NICE IBS guidelines
- **Scoring**: Binary accuracy, precision, recall (recall ≥0.90 — missing a trigger is worse than a false alarm)
- **Targets**: F1 ≥0.85, recall ≥0.90, confounder_mentioned ≥0.70

### Eval 3: Plain English Quality (AI + LLM judge, ~$0.40)
- **What**: 20 cases across trigger types, confidence levels, and states
- **Why**: User-facing explanations should be readable, non-technical, actionable
- **Scoring**: Deterministic (forbidden terms, no raw statistics, sentence count) + LLM-as-judge (readability, relevance, actionability, medical caution)
- **Targets**: readability ≥0.80, forbidden_terms_absent ≥0.95, relevance ≥0.85

### Eval 4: Medical Analysis Quality (AI + LLM judge, ~$0.75)
- **What**: 15 batch analysis cases with mixed confidence levels
- **Why**: Medical context should be relevant, well-cited, ethically sound, with confidence variability
- **Scoring**: LLM judges for relevance, ethics, citation quality + deterministic checks (ingredient coverage, confidence consistency)
- **Targets**: relevance ≥0.80, ethics ≥0.90, citation_quality ≥0.70

### Eval 5: End-to-End Pipeline (~$1.50)
- **What**: 10 full scenarios with 3-5 ingredients each (mix of triggers and bystanders)
- **Why**: Validates the complete flow: scoring → root cause → medical grounding → explanation
- **Scoring**: Kept/discarded precision and recall, plain English pass rate, citations present
- **Targets**: kept_recall ≥0.90, discarded_recall ≥0.85

### Dataset Strategy
- **Primary**: Synthetic — programmatically constructed correlation scenarios with known expected outcomes
- **Ground truth grounding**: Monash FODMAP App, FDA Top 9 Allergens, NICE IBS guidelines, BDA food fact sheets, elimination diet protocols (UW Integrative Health, Stanford Low-FODMAP)
- **Future**: Scrape Monash FODMAP food guide for structured FODMAP ratings per food

## Metrics

### Meal Analysis

| Metric | Formula | Target |
|--------|---------|--------|
| Precision | TP / (TP + FP) | ≥0.80 |
| Recall | TP / (TP + FN) | ≥0.75 |
| F1 Score | 2 × P × R / (P + R) | ≥0.77 |
| State Accuracy | Correct state / Total matched | ≥0.80 |
| Meal Name Similarity | Fuzzy match ratio | ≥0.70 |

**Definitions**:
- **TP**: Predicted ingredient matches expected (with variants)
- **FP**: Predicted ingredient not in expected list
- **FN**: Required expected ingredient not predicted

### Meal Validation

| Metric | Target |
|--------|--------|
| Accuracy | ≥0.95 |
| True Positive Rate | ≥0.98 |
| True Negative Rate | ≥0.90 |

### Diagnosis Confidence

| Metric | Target |
|--------|--------|
| Level Accuracy | ≥0.90 |
| Score in Range | ≥0.95 |
| Distribution Spread | 4 levels |

### Diagnosis Root Cause

| Metric | Target |
|--------|--------|
| Accuracy | ≥0.85 |
| Precision | ≥0.80 |
| Recall | ≥0.90 |
| F1 | ≥0.85 |
| Confounder Mentioned | ≥0.70 |

### Diagnosis Single Ingredient

| Metric | Target |
|--------|--------|
| Readability (LLM judge) | ≥0.80 |
| Relevance (LLM judge) | ≥0.85 |
| Actionability (LLM judge) | ≥0.75 |
| Medical Caution (LLM judge) | ≥0.90 |
| Forbidden Terms Absent | ≥0.95 |
| No Raw Statistics | ≥0.90 |

### Diagnosis Correlations

| Metric | Target |
|--------|--------|
| Ingredient Coverage | 1.0 |
| Relevance (LLM judge) | ≥0.80 |
| Ethics (LLM judge) | ≥0.90 |
| Citation Quality (LLM judge) | ≥0.70 |
| Confidence Consistency | ≥0.80 |

## Results Storage

Results stored in `eval_runs` table (see `app/models/eval_run.py`):

```sql
SELECT model_name, eval_type,
       precision, recall, f1_score,
       num_test_cases, execution_time_seconds,
       created_at
FROM eval_runs
WHERE eval_type = 'meal_analysis'
ORDER BY created_at DESC;
```

**Detailed results** stored in `detailed_results` JSONB column:
- Per-case predictions and scores
- Aggregate metrics
- Error logs
- Config (model, temperature, etc.)

## API Response Caching

To avoid repeated API costs during development:
- Responses cached by request hash in `evals/fixtures/api_cache/`
- Default: use cache (`--use-cache` implicit)
- Fresh calls: `--no-cache` flag
- Cache files: `{method}_{hash}.json`

## Cost Estimates

| Eval Type | Per Case | 100 Cases |
|-----------|----------|-----------|
| Meal Analysis | ~$0.003 | ~$0.30 |
| Meal Validation | ~$0.0005 | ~$0.05 |
| Symptom Elaboration | ~$0.003 | ~$0.30 |
| Diagnosis Confidence | $0 | $0 |
| Diagnosis Root Cause | ~$0.002 | ~$0.08 |
| Diagnosis Single Ingredient | ~$0.02 | ~$0.40 |
| Diagnosis Correlations | ~$0.05 | ~$0.75 |
| Diagnosis E2E | ~$0.15 | ~$1.50 |

## Implementation Phases

### Phase 1: Infrastructure ✅
- [x] EvalRun model exists
- [x] Directory structure
- [x] Base scraper and runner classes
- [x] Metrics implementation (hard + soft/LLM-judge)
- [x] CLI skeleton with all commands

### Phase 2: Meal Analysis ✅
- [x] BBC Good Food scraper
- [x] Download 53 recipe images
- [x] Ground truth JSON format
- [x] MealAnalysisRunner implementation
- [x] Run baseline eval (F1=0.43)
- [x] Prompt versioning infrastructure
- [x] First iteration experiments (F1=0.52)

### Phase 3: Diagnosis Evals ← NEXT
Full plan: `.claude/plans/rosy-zooming-blanket.md`
- [ ] Confidence scoring eval (deterministic, 30 test vectors)
- [ ] Root cause classification eval (40 cases, 20 keep + 20 discard)
- [ ] Single ingredient plain English eval (20 cases + LLM judges)
- [ ] Correlations medical analysis eval (15 cases + LLM judges)
- [ ] End-to-end pipeline eval (10 scenarios)
- [ ] LLM judge prompts for relevance, ethics, plain English, citation quality
- [ ] Prompt versioning for diagnosis methods
- [ ] Config + metric targets for all diagnosis evals

### Phase 4: Secondary Evals
- [ ] AllRecipes scraper
- [ ] Meal validation eval
- [ ] Symptom elaboration eval
- [ ] Edge case images

### Phase 5: Polish ✅
- [x] HTML report generation (`scripts/generate_eval_report.py`)
- [x] History and comparison commands
- [x] Documentation updates

### Phase 6: Iterate to Target
- [ ] Continue meal analysis prompt experiments to F1 ≥0.77
- [ ] State accuracy improvements (currently ~16%)
- [ ] Expand meal dataset to 100 images
- [ ] Iterate diagnosis prompts based on eval results
