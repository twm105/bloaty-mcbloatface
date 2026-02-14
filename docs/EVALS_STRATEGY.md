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
```

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

### Phase 1: Infrastructure
- [x] EvalRun model exists
- [ ] Directory structure
- [ ] Base scraper and runner classes
- [ ] Metrics implementation
- [ ] CLI skeleton

### Phase 2: Meal Analysis (Priority)
- [ ] BBC Good Food scraper
- [ ] Download 50 recipe images
- [ ] Curate ground truth (manual review)
- [ ] MealAnalysisRunner implementation
- [ ] Run first eval

### Phase 3: Secondary Evals
- [ ] AllRecipes scraper
- [ ] Meal validation eval
- [ ] Symptom elaboration eval
- [ ] Edge case images

### Phase 4: Polish
- [ ] HTML report generation
- [ ] History and comparison commands
- [ ] Documentation updates
