#!/usr/bin/env python
"""
Generate static HTML visualization of eval results with version comparison.

Usage:
    # Single run
    docker compose exec web python -m scripts.generate_eval_report --run-id 1

    # Compare multiple runs (baseline vs experiments)
    docker compose exec web python -m scripts.generate_eval_report --run-ids 1,2,3

    # Custom output
    docker compose exec web python -m scripts.generate_eval_report --run-ids 1,2,3 --output comparison.html
"""

import argparse
import base64
import html
from pathlib import Path

from evals.results import get_run_details


def load_image_base64(image_path: str) -> str:
    """Load image and encode as base64 data URI."""
    path = Path("evals/datasets") / image_path
    if not path.exists():
        return ""

    suffix = path.suffix.lower()
    mime_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    mime_type = mime_types.get(suffix, "image/jpeg")

    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{data}"


def get_match_status(
    ingredient_name: str, ingredient_details: dict
) -> tuple[str, float, str]:
    """
    Determine if an expected ingredient was matched by any prediction.

    Returns: (status, score, matched_by)
        - status: 'matched', 'partial', or 'missed'
        - score: best match score (0, 0.5, or 1.0)
        - matched_by: name of predicted ingredient that matched
    """
    prediction_scores = ingredient_details.get("prediction_scores", [])

    best_score = 0.0
    matched_by = None

    for pred in prediction_scores:
        if pred.get("matched_to") == ingredient_name:
            if pred["score"] > best_score:
                best_score = pred["score"]
                matched_by = pred["predicted"]

    if best_score >= 1.0:
        return "matched", best_score, matched_by
    elif best_score >= 0.5:
        return "partial", best_score, matched_by
    else:
        return "missed", 0.0, None


def get_prediction_status(
    predicted: str, ingredient_details: dict
) -> tuple[str, float, str]:
    """
    Determine if a predicted ingredient matched any expected ingredient.

    Returns: (status, score, matched_to)
        - status: 'correct', 'partial', or 'wrong'
        - score: match score (0, 0.5, or 1.0)
        - matched_to: name of expected ingredient it matched
    """
    prediction_scores = ingredient_details.get("prediction_scores", [])

    for pred in prediction_scores:
        if pred["predicted"] == predicted:
            score = pred.get("score", 0)
            matched_to = pred.get("matched_to")

            if score >= 1.0:
                return "correct", score, matched_to
            elif score >= 0.5:
                return "partial", score, matched_to
            else:
                return "wrong", 0.0, None

    return "wrong", 0.0, None


def get_version_label(run_data: dict) -> str:
    """Extract a human-readable version label from run data."""
    detailed = run_data.get("detailed_results", {})
    prompt_version = detailed.get("prompt_version", "")

    if prompt_version and prompt_version != "current":
        return prompt_version

    # Fallback to run ID
    return f"Run {run_data.get('id', '?')}"


def generate_comparison_html(runs_data: list[dict], output_path: str) -> None:
    """Generate HTML visualization comparing multiple eval runs."""

    # Build version info
    versions = []
    for run in runs_data:
        version_label = get_version_label(run)
        aggregate = run.get("detailed_results", {}).get("aggregate", {})
        versions.append(
            {
                "id": run.get("id"),
                "label": version_label,
                "model": run.get("model", "Unknown"),
                "created_at": run.get("created_at", "")[:10]
                if run.get("created_at")
                else "N/A",
                "notes": run.get("detailed_results", {}).get("notes", ""),
                "f1": aggregate.get("mean_f1", 0),
                "precision": aggregate.get("mean_precision", 0),
                "recall": aggregate.get("mean_recall", 0),
                "state_accuracy": aggregate.get("mean_state_accuracy", 0),
                "num_cases": run.get("num_cases", 0),
            }
        )

    # Collect all test cases indexed by ID
    test_cases_by_id = {}
    for run_idx, run in enumerate(runs_data):
        test_cases = run.get("detailed_results", {}).get("test_cases", [])
        for case in test_cases:
            case_id = case.get("id", "unknown")
            if case_id not in test_cases_by_id:
                test_cases_by_id[case_id] = {
                    "id": case_id,
                    "image_path": case.get("image_path", ""),
                    "expected": case.get("expected", {}),
                    "versions": {},
                }
            test_cases_by_id[case_id]["versions"][run_idx] = {
                "predicted": case.get("predicted", {}),
                "score": case.get("score", {}),
                "ingredient_details": case.get("ingredient_details", {}),
            }

    # Sort test cases by ID
    sorted_case_ids = sorted(test_cases_by_id.keys())

    def get_score_class(score):
        if score >= 0.7:
            return "good"
        elif score >= 0.4:
            return "medium"
        return "poor"

    # Start building HTML
    html_parts = [
        """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Meal Analysis Eval Comparison</title>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            color: #333;
            line-height: 1.5;
            padding: 20px;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
        }

        h1 {
            font-size: 1.8rem;
            margin-bottom: 10px;
            color: #1a1a1a;
        }

        h2 {
            font-size: 1.2rem;
            margin-bottom: 10px;
            color: #333;
        }

        /* Summary Section */
        .summary {
            background: white;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 30px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }

        /* Version Comparison Table */
        .comparison-table {
            width: 100%;
            border-collapse: collapse;
            margin: 16px 0;
            font-size: 0.95rem;
        }

        .comparison-table th,
        .comparison-table td {
            padding: 12px 16px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }

        .comparison-table th {
            background: #f8f9fa;
            font-weight: 600;
            color: #555;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }

        .comparison-table tr:hover {
            background: #f8f9fa;
        }

        .comparison-table .metric-cell {
            font-weight: 600;
            font-variant-numeric: tabular-nums;
        }

        .comparison-table .metric-cell.good { color: #16a34a; }
        .comparison-table .metric-cell.medium { color: #d97706; }
        .comparison-table .metric-cell.poor { color: #dc2626; }

        .comparison-table .best {
            background: #dcfce7;
        }

        .version-label {
            font-weight: 600;
            color: #1a1a1a;
        }

        .version-notes {
            font-size: 0.85rem;
            color: #666;
            margin-top: 4px;
        }

        .delta {
            font-size: 0.8rem;
            margin-left: 6px;
        }

        .delta.positive { color: #16a34a; }
        .delta.negative { color: #dc2626; }

        /* Version Tabs */
        .version-tabs {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin-bottom: 20px;
        }

        .version-tab {
            padding: 8px 16px;
            border: 2px solid #e5e5e5;
            border-radius: 8px;
            background: white;
            cursor: pointer;
            font-size: 0.9rem;
            font-weight: 500;
            transition: all 0.15s ease;
        }

        .version-tab:hover {
            border-color: #2563eb;
            background: #eff6ff;
        }

        .version-tab.active {
            border-color: #2563eb;
            background: #2563eb;
            color: white;
        }

        .version-tab .tab-score {
            font-size: 0.8rem;
            opacity: 0.8;
            margin-left: 6px;
        }

        /* Test Case Cards */
        .test-case {
            background: white;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            overflow: hidden;
        }

        .test-case-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px 20px;
            background: #f8f9fa;
            border-bottom: 1px solid #eee;
            flex-wrap: wrap;
            gap: 12px;
        }

        .test-case-id {
            font-weight: 600;
            color: #333;
        }

        .score-badges {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }

        .score-badge {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 6px 12px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.85rem;
        }

        .score-badge.good { background: #dcfce7; color: #166534; }
        .score-badge.medium { background: #fef3c7; color: #92400e; }
        .score-badge.poor { background: #fee2e2; color: #991b1b; }

        .score-badge .version-name {
            font-weight: 500;
            opacity: 0.8;
        }

        .test-case-body {
            display: grid;
            grid-template-columns: 200px 1fr 1fr;
            gap: 20px;
            padding: 20px;
        }

        @media (max-width: 900px) {
            .test-case-body {
                grid-template-columns: 1fr;
            }
        }

        .image-col {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .meal-image {
            width: 100%;
            height: 180px;
            object-fit: cover;
            border-radius: 8px;
            background: #e5e5e5;
        }

        .column-header {
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #888;
            margin-bottom: 8px;
        }

        .meal-title {
            font-weight: 600;
            font-size: 1rem;
            margin-bottom: 12px;
            color: #1a1a1a;
        }

        .ingredients-list {
            list-style: none;
        }

        .ingredient {
            padding: 4px 8px;
            margin: 2px 0;
            border-radius: 4px;
            font-size: 0.9rem;
        }

        /* Ground truth colors */
        .ingredient.matched {
            background: #dcfce7;
            color: #166534;
        }

        .ingredient.partial {
            background: #fef3c7;
            color: #92400e;
        }

        .ingredient.missed {
            background: #fee2e2;
            color: #991b1b;
        }

        /* Prediction colors */
        .ingredient.correct {
            background: #dcfce7;
            color: #166534;
        }

        .ingredient.wrong {
            background: #fee2e2;
            color: #991b1b;
        }

        .match-info {
            font-size: 0.75rem;
            opacity: 0.8;
        }

        .legend {
            display: flex;
            gap: 16px;
            flex-wrap: wrap;
            margin-top: 12px;
            font-size: 0.85rem;
        }

        .legend-item {
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .legend-swatch {
            width: 16px;
            height: 16px;
            border-radius: 4px;
        }

        .legend-swatch.green { background: #dcfce7; border: 1px solid #86efac; }
        .legend-swatch.yellow { background: #fef3c7; border: 1px solid #fcd34d; }
        .legend-swatch.red { background: #fee2e2; border: 1px solid #fca5a5; }

        /* Version content */
        .version-content {
            display: none;
        }

        .version-content.active {
            display: block;
        }

        .predictions-wrapper {
            position: relative;
        }

        .prediction-version {
            display: none;
        }

        .prediction-version.active {
            display: block;
        }
    </style>
</head>
<body>
    <div class="container">
"""
    ]

    # Find best scores for highlighting
    best_f1 = max(v["f1"] for v in versions) if versions else 0
    baseline_f1 = versions[0]["f1"] if versions else 0

    # Summary section with comparison table
    html_parts.append(f"""
        <div class="summary">
            <h1>Meal Analysis Eval Comparison</h1>
            <p style="color: #666; margin-bottom: 16px;">
                Comparing {len(versions)} prompt versions. Select a version below to view per-case predictions.
            </p>

            <table class="comparison-table">
                <thead>
                    <tr>
                        <th>Version</th>
                        <th>F1 Score</th>
                        <th>Precision</th>
                        <th>Recall</th>
                        <th>State Acc</th>
                        <th>Cases</th>
                        <th>Date</th>
                    </tr>
                </thead>
                <tbody>
""")

    for i, v in enumerate(versions):
        is_best = v["f1"] == best_f1 and len(versions) > 1
        row_class = "best" if is_best else ""

        # Calculate delta from baseline
        delta_f1 = v["f1"] - baseline_f1 if i > 0 else 0
        delta_html = ""
        if i > 0:
            delta_class = (
                "positive" if delta_f1 > 0 else "negative" if delta_f1 < 0 else ""
            )
            delta_sign = "+" if delta_f1 > 0 else ""
            delta_html = (
                f'<span class="delta {delta_class}">{delta_sign}{delta_f1:.1%}</span>'
            )

        notes_html = (
            f'<div class="version-notes">{html.escape(v["notes"][:60])}...</div>'
            if v["notes"]
            else ""
        )

        html_parts.append(f"""
                    <tr class="{row_class}">
                        <td>
                            <div class="version-label">{html.escape(v["label"])}</div>
                            {notes_html}
                        </td>
                        <td class="metric-cell {get_score_class(v["f1"])}">{v["f1"]:.1%}{delta_html}</td>
                        <td class="metric-cell {get_score_class(v["precision"])}">{v["precision"]:.1%}</td>
                        <td class="metric-cell {get_score_class(v["recall"])}">{v["recall"]:.1%}</td>
                        <td class="metric-cell {get_score_class(v["state_accuracy"])}">{v["state_accuracy"]:.1%}</td>
                        <td>{v["num_cases"]}</td>
                        <td>{v["created_at"]}</td>
                    </tr>
""")

    html_parts.append("""
                </tbody>
            </table>

            <div class="legend">
                <div class="legend-item">
                    <div class="legend-swatch green"></div>
                    <span>Full match (1.0)</span>
                </div>
                <div class="legend-item">
                    <div class="legend-swatch yellow"></div>
                    <span>Partial match (0.5)</span>
                </div>
                <div class="legend-item">
                    <div class="legend-swatch red"></div>
                    <span>No match / Wrong</span>
                </div>
            </div>
        </div>
""")

    # Version selector tabs
    html_parts.append("""
        <h2>Test Cases</h2>
        <div class="version-tabs">
""")

    for i, v in enumerate(versions):
        active_class = "active" if i == 0 else ""
        html_parts.append(f"""
            <button class="version-tab {active_class}" data-version="{i}">
                {html.escape(v["label"])}
                <span class="tab-score">F1: {v["f1"]:.0%}</span>
            </button>
""")

    html_parts.append("</div>")

    # Test case cards
    for case_id in sorted_case_ids:
        case_data = test_cases_by_id[case_id]
        image_path = case_data["image_path"]
        expected = case_data["expected"]

        # Load image
        image_data = load_image_base64(image_path)

        # Score badges for all versions
        score_badges_html = []
        for i, v in enumerate(versions):
            version_data = case_data["versions"].get(i, {})
            score = version_data.get("score", {})
            f1 = score.get("f1", 0)
            score_badges_html.append(
                f'<span class="score-badge {get_score_class(f1)}" data-version="{i}">'
                f'<span class="version-name">{html.escape(v["label"][:10])}:</span> {f1:.0%}'
                f"</span>"
            )

        html_parts.append(f"""
        <div class="test-case">
            <div class="test-case-header">
                <span class="test-case-id">{html.escape(case_id)}</span>
                <div class="score-badges">
                    {"".join(score_badges_html)}
                </div>
            </div>
            <div class="test-case-body">
                <div class="image-col">
                    <div class="column-header">Image</div>
                    {"<img class='meal-image' src='" + image_data + "' alt='Meal image'>" if image_data else "<div class='meal-image' style='display:flex;align-items:center;justify-content:center;color:#999;'>No image</div>"}
                </div>
                <div>
                    <div class="column-header">Ground Truth ({len(expected.get("ingredients", []))} ingredients)</div>
                    <div class="meal-title">{html.escape(expected.get("meal_name", "Unknown"))}</div>
""")

        # Build ground truth ingredients per version (colors change based on selected version)
        for i, v in enumerate(versions):
            version_data = case_data["versions"].get(i, {})
            ingredient_details = version_data.get("ingredient_details", {})

            active_class = "active" if i == 0 else ""

            expected_ingredients_html = []
            for ing in expected.get("ingredients", []):
                ing_name = ing.get("name", "Unknown")
                raw_text = ing.get("raw_text", ing_name)
                required = ing.get("required", True)

                status, match_score, matched_by = get_match_status(
                    ing_name, ingredient_details
                )

                status_class = status
                match_info = ""
                if matched_by and status != "missed":
                    match_info = f' <span class="match-info">(matched by: {html.escape(matched_by)})</span>'

                display_text = html.escape(raw_text)
                if not required:
                    display_text = f"<em>{display_text}</em> (optional)"

                expected_ingredients_html.append(
                    f'<li class="ingredient {status_class}">{display_text}{match_info}</li>'
                )

            html_parts.append(f"""
                    <ul class="ingredients-list prediction-version {active_class}" data-version="{i}">
                        {"".join(expected_ingredients_html)}
                    </ul>
""")

        html_parts.append("""
                </div>
                <div class="predictions-wrapper">
""")

        # Predictions for each version
        for i, v in enumerate(versions):
            version_data = case_data["versions"].get(i, {})
            predicted = version_data.get("predicted", {})
            ingredient_details = version_data.get("ingredient_details", {})

            active_class = "active" if i == 0 else ""

            predicted_ingredients_html = []
            for ing in predicted.get("ingredients", []):
                if isinstance(ing, dict):
                    ing_name = ing.get("name", "Unknown")
                    ing_state = ing.get("state", "")
                else:
                    ing_name = str(ing)
                    ing_state = ""

                status, match_score, matched_to = get_prediction_status(
                    ing_name, ingredient_details
                )

                match_info = ""
                if matched_to:
                    score_str = "full" if match_score >= 1.0 else "partial"
                    match_info = f' <span class="match-info">({score_str}: {html.escape(matched_to)})</span>'

                display_text = html.escape(ing_name)
                if ing_state:
                    display_text += f" <em>({ing_state})</em>"

                predicted_ingredients_html.append(
                    f'<li class="ingredient {status}">{display_text}{match_info}</li>'
                )

            html_parts.append(f"""
                    <div class="prediction-version {active_class}" data-version="{i}">
                        <div class="column-header">Predicted - {html.escape(v["label"])} ({len(predicted.get("ingredients", []))} ingredients)</div>
                        <div class="meal-title">{html.escape(predicted.get("meal_name", "Unknown"))}</div>
                        <ul class="ingredients-list">
                            {"".join(predicted_ingredients_html)}
                        </ul>
                    </div>
""")

        html_parts.append("""
                </div>
            </div>
        </div>
""")

    # JavaScript for version switching
    html_parts.append("""
    </div>

    <script>
        document.addEventListener('DOMContentLoaded', function() {
            const tabs = document.querySelectorAll('.version-tab');

            tabs.forEach(tab => {
                tab.addEventListener('click', function() {
                    const version = this.dataset.version;

                    // Update tab active state
                    tabs.forEach(t => t.classList.remove('active'));
                    this.classList.add('active');

                    // Update all version-specific content
                    document.querySelectorAll('.prediction-version').forEach(el => {
                        el.classList.remove('active');
                        if (el.dataset.version === version) {
                            el.classList.add('active');
                        }
                    });
                });
            });
        });
    </script>
</body>
</html>
""")

    # Write to file
    output = Path(output_path)
    output.write_text("".join(html_parts))
    print(f"Generated comparison report: {output.absolute()}")


def generate_single_html(run_data: dict, output_path: str) -> None:
    """Generate HTML visualization for a single eval run (backward compatible)."""
    generate_comparison_html([run_data], output_path)


def main():
    parser = argparse.ArgumentParser(description="Generate HTML eval report")
    parser.add_argument(
        "--run-id",
        type=int,
        help="Single eval run ID to visualize",
    )
    parser.add_argument(
        "--run-ids",
        type=str,
        help="Comma-separated list of run IDs to compare (e.g., 1,2,3)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="evals/reports/eval_report.html",
        help="Output HTML file path",
    )

    args = parser.parse_args()

    # Determine run IDs
    if args.run_ids:
        run_ids = [int(x.strip()) for x in args.run_ids.split(",")]
    elif args.run_id:
        run_ids = [args.run_id]
    else:
        print("Error: Must specify --run-id or --run-ids")
        return 1

    # Load all run data
    runs_data = []
    for run_id in run_ids:
        run_data = get_run_details(run_id)
        if not run_data:
            print(f"Error: Run ID {run_id} not found")
            return 1
        runs_data.append(run_data)

    # Ensure output directory exists
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate HTML
    generate_comparison_html(runs_data, args.output)
    return 0


if __name__ == "__main__":
    exit(main())
