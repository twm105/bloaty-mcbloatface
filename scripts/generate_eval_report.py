#!/usr/bin/env python
"""
Generate static HTML visualization of eval results.

Usage:
    docker compose exec web python -m scripts.generate_eval_report --run-id 1
    docker compose exec web python -m scripts.generate_eval_report --run-id 1 --output report.html
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


def get_match_status(ingredient_name: str, ingredient_details: dict) -> tuple[str, float, str]:
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


def get_prediction_status(predicted: str, ingredient_details: dict) -> tuple[str, float, str]:
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


def generate_html(run_data: dict, output_path: str) -> None:
    """Generate HTML visualization from eval run data."""

    test_cases = run_data.get("detailed_results", {}).get("test_cases", [])
    aggregate = run_data.get("detailed_results", {}).get("aggregate", {})

    # Start building HTML
    html_parts = [
        """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Meal Analysis Eval Report</title>
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
            margin-bottom: 20px;
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

        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 20px;
            margin-top: 16px;
        }

        .metric-card {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 16px;
            text-align: center;
        }

        .metric-value {
            font-size: 2rem;
            font-weight: 700;
            color: #2563eb;
        }

        .metric-value.good { color: #16a34a; }
        .metric-value.medium { color: #d97706; }
        .metric-value.poor { color: #dc2626; }

        .metric-label {
            font-size: 0.85rem;
            color: #666;
            margin-top: 4px;
        }

        .meta-info {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            margin-top: 16px;
            padding-top: 16px;
            border-top: 1px solid #eee;
            font-size: 0.9rem;
            color: #666;
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
        }

        .test-case-id {
            font-weight: 600;
            color: #333;
        }

        .score-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 6px 12px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.9rem;
        }

        .score-badge.good { background: #dcfce7; color: #166534; }
        .score-badge.medium { background: #fef3c7; color: #92400e; }
        .score-badge.poor { background: #fee2e2; color: #991b1b; }

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
    </style>
</head>
<body>
    <div class="container">
"""
    ]

    # Summary section
    mean_f1 = aggregate.get("mean_f1", 0)
    mean_precision = aggregate.get("mean_precision", 0)
    mean_recall = aggregate.get("mean_recall", 0)
    mean_state_acc = aggregate.get("mean_state_accuracy", 0)

    def get_score_class(score):
        if score >= 0.7:
            return "good"
        elif score >= 0.4:
            return "medium"
        return "poor"

    html_parts.append(f"""
        <div class="summary">
            <h1>Meal Analysis Eval Report</h1>
            <div class="summary-grid">
                <div class="metric-card">
                    <div class="metric-value {get_score_class(mean_f1)}">{mean_f1:.1%}</div>
                    <div class="metric-label">Mean Soft F1</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value {get_score_class(mean_precision)}">{mean_precision:.1%}</div>
                    <div class="metric-label">Mean Precision</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value {get_score_class(mean_recall)}">{mean_recall:.1%}</div>
                    <div class="metric-label">Mean Recall</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value {get_score_class(mean_state_acc)}">{mean_state_acc:.1%}</div>
                    <div class="metric-label">State Accuracy</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{run_data.get('num_cases', 0)}</div>
                    <div class="metric-label">Test Cases</div>
                </div>
            </div>
            <div class="meta-info">
                <span><strong>Model:</strong> {html.escape(run_data.get('model', 'Unknown'))}</span>
                <span><strong>Run ID:</strong> {run_data.get('id', 'N/A')}</span>
                <span><strong>Date:</strong> {run_data.get('created_at', 'N/A')[:10] if run_data.get('created_at') else 'N/A'}</span>
                <span><strong>Execution Time:</strong> {run_data.get('execution_time', 0):.1f}s</span>
            </div>
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

        <h2>Test Cases</h2>
""")

    # Test case cards
    for case in test_cases:
        case_id = case.get("id", "unknown")
        image_path = case.get("image_path", "")
        expected = case.get("expected", {})
        predicted = case.get("predicted", {})
        score = case.get("score", {})
        ingredient_details = case.get("ingredient_details", {})

        f1 = score.get("f1", 0)
        precision = score.get("precision", 0)
        recall = score.get("recall", 0)

        # Load image
        image_data = load_image_base64(image_path)

        # Build expected ingredients HTML
        expected_ingredients_html = []
        for ing in expected.get("ingredients", []):
            ing_name = ing.get("name", "Unknown")
            raw_text = ing.get("raw_text", ing_name)
            required = ing.get("required", True)

            status, match_score, matched_by = get_match_status(ing_name, ingredient_details)

            status_class = status  # matched, partial, or missed
            match_info = ""
            if matched_by and status != "missed":
                match_info = f' <span class="match-info">(matched by: {html.escape(matched_by)})</span>'

            # Show with strikethrough if not required
            display_text = html.escape(raw_text)
            if not required:
                display_text = f"<em>{display_text}</em> (optional)"

            expected_ingredients_html.append(
                f'<li class="ingredient {status_class}">{display_text}{match_info}</li>'
            )

        # Build predicted ingredients HTML
        predicted_ingredients_html = []
        for ing in predicted.get("ingredients", []):
            if isinstance(ing, dict):
                ing_name = ing.get("name", "Unknown")
                ing_state = ing.get("state", "")
            else:
                ing_name = str(ing)
                ing_state = ""

            status, match_score, matched_to = get_prediction_status(ing_name, ingredient_details)

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

        score_class = get_score_class(f1)

        html_parts.append(f"""
        <div class="test-case">
            <div class="test-case-header">
                <span class="test-case-id">{html.escape(case_id)}</span>
                <span class="score-badge {score_class}">
                    F1: {f1:.1%} | P: {precision:.1%} | R: {recall:.1%}
                </span>
            </div>
            <div class="test-case-body">
                <div class="image-col">
                    <div class="column-header">Image</div>
                    {"<img class='meal-image' src='" + image_data + "' alt='Meal image'>" if image_data else "<div class='meal-image' style='display:flex;align-items:center;justify-content:center;color:#999;'>No image</div>"}
                </div>
                <div>
                    <div class="column-header">Ground Truth ({len(expected.get('ingredients', []))} ingredients)</div>
                    <div class="meal-title">{html.escape(expected.get('meal_name', 'Unknown'))}</div>
                    <ul class="ingredients-list">
                        {''.join(expected_ingredients_html)}
                    </ul>
                </div>
                <div>
                    <div class="column-header">Predicted ({len(predicted.get('ingredients', []))} ingredients)</div>
                    <div class="meal-title">{html.escape(predicted.get('meal_name', 'Unknown'))}</div>
                    <ul class="ingredients-list">
                        {''.join(predicted_ingredients_html)}
                    </ul>
                </div>
            </div>
        </div>
""")

    # Close HTML
    html_parts.append("""
    </div>
</body>
</html>
""")

    # Write to file
    output = Path(output_path)
    output.write_text("".join(html_parts))
    print(f"Generated report: {output.absolute()}")


def main():
    parser = argparse.ArgumentParser(description="Generate HTML eval report")
    parser.add_argument(
        "--run-id",
        type=int,
        required=True,
        help="Eval run ID to visualize",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="evals/reports/eval_report.html",
        help="Output HTML file path",
    )

    args = parser.parse_args()

    # Get run data
    run_data = get_run_details(args.run_id)
    if not run_data:
        print(f"Error: Run ID {args.run_id} not found")
        return 1

    # Ensure output directory exists
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate HTML
    generate_html(run_data, args.output)
    return 0


if __name__ == "__main__":
    exit(main())
