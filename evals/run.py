#!/usr/bin/env python
"""
Evaluation runner CLI for Bloaty McBloatface AI features.

Usage:
    python -m evals.run eval --eval-type meal_analysis
    python -m evals.run eval --eval-type meal_analysis --sample 10 --verbose
    python -m evals.run scrape --source bbc_good_food --limit 50
    python -m evals.run history --eval-type meal_analysis
    python -m evals.run compare --runs 1,2,3
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from evals.config import EvalConfig, DEFAULT_MODEL


def main():
    parser = argparse.ArgumentParser(
        description="Run evaluations for Bloaty McBloatface AI features"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Eval command
    eval_parser = subparsers.add_parser("eval", help="Run evaluations")
    eval_parser.add_argument(
        "--eval-type",
        choices=["meal_analysis", "meal_validation", "symptom_elaboration", "all"],
        required=True,
        help="Type of evaluation to run",
    )
    eval_parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model to evaluate (default: {DEFAULT_MODEL})",
    )
    eval_parser.add_argument(
        "--sample",
        type=int,
        help="Limit to N test cases (for quick testing)",
    )
    eval_parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable API response caching (incurs costs)",
    )
    eval_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print detailed progress",
    )
    eval_parser.add_argument(
        "--output",
        choices=["json", "table"],
        default="table",
        help="Output format",
    )
    eval_parser.add_argument(
        "--no-store",
        action="store_true",
        help="Don't store results in database",
    )
    eval_parser.add_argument(
        "--no-llm-judge",
        action="store_true",
        help="Disable LLM-as-judge soft scoring (use hard string matching)",
    )

    # Scrape command
    scrape_parser = subparsers.add_parser("scrape", help="Scrape recipe data")
    scrape_parser.add_argument(
        "--source",
        choices=["bbc_good_food", "allrecipes"],
        required=True,
        help="Recipe source to scrape",
    )
    scrape_parser.add_argument(
        "--category",
        help="Category to scrape (e.g., 'chicken-recipes')",
    )
    scrape_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum recipes to scrape (default: 50)",
    )
    scrape_parser.add_argument(
        "--download-images",
        action="store_true",
        help="Also download recipe images",
    )
    scrape_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evals/datasets/meal_images"),
        help="Output directory for images",
    )

    # History command
    history_parser = subparsers.add_parser("history", help="View eval history")
    history_parser.add_argument(
        "--eval-type",
        required=True,
        help="Filter by eval type",
    )
    history_parser.add_argument(
        "--model",
        help="Filter by model name",
    )
    history_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of runs to show (default: 10)",
    )

    # Compare command
    compare_parser = subparsers.add_parser("compare", help="Compare eval runs")
    compare_parser.add_argument(
        "--runs",
        required=True,
        help="Comma-separated run IDs to compare",
    )

    # Cache command
    cache_parser = subparsers.add_parser("cache", help="Manage API response cache")
    cache_parser.add_argument(
        "--stats",
        action="store_true",
        help="Show cache statistics",
    )
    cache_parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear all cached responses",
    )
    cache_parser.add_argument(
        "--method",
        help="Only clear caches for this method (with --clear)",
    )

    args = parser.parse_args()

    if args.command == "eval":
        asyncio.run(run_eval(args))
    elif args.command == "scrape":
        run_scrape(args)
    elif args.command == "history":
        run_history(args)
    elif args.command == "compare":
        run_compare(args)
    elif args.command == "cache":
        run_cache(args)


async def run_eval(args):
    """Execute evaluation run."""
    from evals.runners import get_runner
    from evals.results import store_eval_result

    config = EvalConfig(
        model=args.model,
        eval_type=args.eval_type,
        dataset_path=Path("evals/datasets"),
        use_cache=not args.no_cache,
        sample_size=args.sample,
        verbose=args.verbose,
        use_llm_judge=not args.no_llm_judge,
    )

    try:
        runner = get_runner(config)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    scoring_mode = "LLM-judge soft scoring" if config.use_llm_judge else "hard string matching"
    print(f"Running {config.eval_type} eval with {config.model}...")
    print(f"Scoring mode: {scoring_mode}")

    result = await runner.run()

    # Store in database
    run_id = None
    if not args.no_store:
        try:
            run_id = store_eval_result(result)
            print(f"\nStored as run ID: {run_id}")
        except Exception as e:
            print(f"\nWarning: Could not store results: {e}", file=sys.stderr)

    # Output results
    if args.output == "table":
        print_table(result)
    else:
        print_json(result)


def run_scrape(args):
    """Execute recipe scraping."""
    from evals.scrapers.bbc_good_food import BBCGoodFoodScraper
    from evals.scrapers.allrecipes import AllRecipesScraper

    scrapers = {
        "bbc_good_food": BBCGoodFoodScraper,
        "allrecipes": AllRecipesScraper,
    }

    scraper_class = scrapers.get(args.source)
    if not scraper_class:
        print(f"Unknown source: {args.source}", file=sys.stderr)
        sys.exit(1)

    scraper = scraper_class(output_dir=args.output_dir)

    # Default categories per source
    default_categories = {
        "bbc_good_food": "chicken-recipes",
        "allrecipes": "quick-and-easy-recipes",
    }

    category = args.category or default_categories.get(args.source, "")

    print(f"Scraping {args.source} - {category} (limit: {args.limit})...")

    recipes = scraper.scrape_category(
        category=category,
        limit=args.limit,
        download_images=args.download_images,
    )

    print(f"\nScraped {len(recipes)} recipes:")
    for recipe in recipes:
        ing_count = len(recipe.ingredients)
        has_image = "+" if recipe.local_image_path else "-"
        print(f"  [{has_image}] {recipe.recipe_name} ({ing_count} ingredients)")

    # Generate ground truth skeleton
    if recipes:
        gt_path = Path("evals/datasets/ground_truth")
        gt_path.mkdir(parents=True, exist_ok=True)

        gt_file = gt_path / f"{args.source}_scraped.json"

        ground_truth = {
            "version": "1.0",
            "source": args.source,
            "test_cases": [],
        }

        for recipe in recipes:
            # Convert ingredients to ground truth format
            ingredients = []
            for ing in recipe.ingredients:
                ingredients.append(
                    {
                        "name": ing.name,
                        "name_variants": [],
                        "state": ing.state or "raw",
                        "required": True,
                    }
                )

            test_case = {
                "id": f"{args.source}_{recipe.slug}",
                "source": args.source,
                "source_url": recipe.source_url,
                "image_path": str(
                    recipe.local_image_path.relative_to(Path("evals/datasets"))
                )
                if recipe.local_image_path
                else None,
                "expected": {
                    "meal_name": recipe.recipe_name,
                    "meal_name_alternatives": [],
                    "ingredients": ingredients,
                },
                "difficulty": "medium",
                "notes": "",
            }
            ground_truth["test_cases"].append(test_case)

        with open(gt_file, "w") as f:
            json.dump(ground_truth, f, indent=2)

        print(f"\nGenerated ground truth skeleton: {gt_file}")
        print("  Review and add name_variants for ingredient fuzzy matching")


def run_history(args):
    """Show eval run history."""
    from evals.results import get_eval_history

    try:
        runs = get_eval_history(
            eval_type=args.eval_type,
            model=args.model,
            limit=args.limit,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not runs:
        print(f"No eval runs found for {args.eval_type}")
        return

    print(f"\nRecent {args.eval_type} eval runs:")
    print("-" * 80)
    print(
        f"{'ID':<6} {'Model':<30} {'F1':<8} {'P':<8} {'R':<8} {'Cases':<6} {'Time':<8}"
    )
    print("-" * 80)

    for run in runs:
        f1 = f"{run['f1']:.4f}" if run.get("f1") else "N/A"
        p = f"{run['precision']:.4f}" if run.get("precision") else "N/A"
        r = f"{run['recall']:.4f}" if run.get("recall") else "N/A"
        cases = run.get("num_cases") or "N/A"
        time = f"{run['execution_time']:.1f}s" if run.get("execution_time") else "N/A"
        model = (run.get("model") or "unknown")[:28]

        print(f"{run['id']:<6} {model:<30} {f1:<8} {p:<8} {r:<8} {cases:<6} {time:<8}")


def run_compare(args):
    """Compare eval runs."""
    from evals.results import compare_runs

    try:
        run_ids = [int(x.strip()) for x in args.runs.split(",")]
    except ValueError:
        print("Error: --runs must be comma-separated integers", file=sys.stderr)
        sys.exit(1)

    try:
        comparison = compare_runs(run_ids)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    runs = comparison.get("runs", [])
    if not runs:
        print("No runs found with those IDs")
        return

    print("\nRun Comparison:")
    print("-" * 70)
    print(f"{'ID':<6} {'Model':<25} {'Type':<15} {'F1':<8} {'P':<8} {'R':<8}")
    print("-" * 70)

    for run in runs:
        f1 = f"{run['f1']:.4f}" if run.get("f1") else "N/A"
        p = f"{run['precision']:.4f}" if run.get("precision") else "N/A"
        r = f"{run['recall']:.4f}" if run.get("recall") else "N/A"
        model = (run.get("model") or "unknown")[:23]
        eval_type = (run.get("eval_type") or "unknown")[:13]

        print(f"{run['id']:<6} {model:<25} {eval_type:<15} {f1:<8} {p:<8} {r:<8}")


def run_cache(args):
    """Manage API response cache."""
    from evals.fixtures.cache_manager import CacheManager

    cache = CacheManager()

    if args.stats:
        stats = cache.stats()
        print("\nCache Statistics:")
        print(f"  Files: {stats['file_count']}")
        print(f"  Size: {stats['total_size_bytes'] / 1024:.1f} KB")
        print("  Methods:")
        for method, count in stats.get("methods", {}).items():
            print(f"    {method}: {count}")

    elif args.clear:
        count = cache.clear(method=args.method)
        scope = f"for {args.method}" if args.method else "(all)"
        print(f"Cleared {count} cached responses {scope}")

    else:
        # Default to stats
        stats = cache.stats()
        print(
            f"Cache: {stats['file_count']} files, {stats['total_size_bytes'] / 1024:.1f} KB"
        )


def print_table(result):
    """Print results as ASCII table."""
    print(f"\n{'=' * 60}")
    print(f"Eval Type: {result.eval_type}")
    print(f"Model: {result.model}")
    print(f"Test Cases: {result.num_cases}")
    print(f"Execution Time: {result.execution_time_seconds:.2f}s")
    print(f"{'=' * 60}")

    print("\nMetrics:")
    for key, value in sorted(result.metrics.items()):
        if isinstance(value, float):
            print(f"  {key}: {value:.4f}")
        else:
            print(f"  {key}: {value}")

    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for err in result.errors[:5]:
            print(f"  - {err['case_id']}: {err['error']}")
        if len(result.errors) > 5:
            print(f"  ... and {len(result.errors) - 5} more")


def print_json(result):
    """Print results as JSON."""
    output = {
        "eval_type": result.eval_type,
        "model": result.model,
        "num_cases": result.num_cases,
        "execution_time_seconds": result.execution_time_seconds,
        "metrics": result.metrics,
        "errors": result.errors,
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
