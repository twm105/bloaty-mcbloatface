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
| Diagnosis | `diagnose_correlations()` | P4 | JSON Validity, Citation Quality | Manual review |

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
├── scrapers/
│   ├── base.py                 # Abstract scraper
│   ├── bbc_good_food.py        # BBC Good Food
│   └── allrecipes.py           # AllRecipes
├── datasets/
│   ├── meal_images/            # Images (gitignored)
│   ├── ground_truth/           # JSON truth files
│   └── manifest.yaml           # Metadata
├── runners/
│   ├── base.py                 # BaseEvalRunner ABC
│   └── meal_analysis.py        # Meal analysis eval
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

### Phase 3: Secondary Evals
- [ ] AllRecipes scraper
- [ ] Meal validation eval
- [ ] Symptom elaboration eval
- [ ] Edge case images

### Phase 4: Polish ✅
- [x] HTML report generation (`scripts/generate_eval_report.py`)
- [x] History and comparison commands
- [x] Documentation updates

### Phase 5: Iterate to Target
- [ ] Continue prompt experiments to F1 ≥0.77
- [ ] State accuracy improvements (currently ~16%)
- [ ] Expand dataset to 100 images
