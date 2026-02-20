"""Database storage and retrieval for eval results."""

from dataclasses import dataclass


@dataclass
class EvalResult:
    """Result from an evaluation run."""

    eval_type: str
    model: str
    num_cases: int
    metrics: dict
    detailed_results: list[dict]
    execution_time_seconds: float
    errors: list[dict]
    prompt_version: str = "current"
    notes: str = ""


def store_eval_result(result: EvalResult) -> int:
    """Store eval result in database and return run ID.

    Args:
        result: EvalResult from a runner

    Returns:
        Database ID of the created eval_run record
    """
    from app.database import SessionLocal
    from app.models.eval_run import EvalRun

    db = SessionLocal()
    try:
        run = EvalRun(
            model_name=result.model,
            eval_type=result.eval_type,
            precision=result.metrics.get("mean_precision")
            or result.metrics.get("precision"),
            recall=result.metrics.get("mean_recall")
            or result.metrics.get("recall"),
            f1_score=result.metrics.get("mean_f1") or result.metrics.get("f1"),
            accuracy=result.metrics.get("accuracy"),
            num_test_cases=result.num_cases,
            test_data_source="scraped_recipes",
            detailed_results={
                "test_cases": result.detailed_results,
                "aggregate": result.metrics,
                "errors": result.errors,
                "prompt_version": result.prompt_version,
            },
            execution_time_seconds=result.execution_time_seconds,
            notes=result.notes if result.notes else None,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run.id
    finally:
        db.close()


def get_eval_history(
    eval_type: str,
    model: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Retrieve recent eval runs for comparison.

    Args:
        eval_type: Filter by evaluation type (e.g., 'meal_analysis')
        model: Optional model name filter
        limit: Maximum number of runs to return

    Returns:
        List of eval run dicts with key metrics
    """
    from app.database import SessionLocal
    from app.models.eval_run import EvalRun

    db = SessionLocal()
    try:
        query = db.query(EvalRun).filter(EvalRun.eval_type == eval_type)
        if model:
            query = query.filter(EvalRun.model_name == model)

        runs = query.order_by(EvalRun.created_at.desc()).limit(limit).all()

        return [
            {
                "id": r.id,
                "model": r.model_name,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "precision": float(r.precision) if r.precision else None,
                "recall": float(r.recall) if r.recall else None,
                "f1": float(r.f1_score) if r.f1_score else None,
                "accuracy": float(r.accuracy) if r.accuracy else None,
                "num_cases": r.num_test_cases,
                "execution_time": float(r.execution_time_seconds)
                if r.execution_time_seconds
                else None,
            }
            for r in runs
        ]
    finally:
        db.close()


def compare_runs(run_ids: list[int]) -> dict:
    """Compare metrics across multiple eval runs.

    Args:
        run_ids: List of eval_run IDs to compare

    Returns:
        Dict with runs list containing metrics for each run
    """
    from app.database import SessionLocal
    from app.models.eval_run import EvalRun

    db = SessionLocal()
    try:
        runs = db.query(EvalRun).filter(EvalRun.id.in_(run_ids)).all()
        return {
            "runs": [
                {
                    "id": r.id,
                    "model": r.model_name,
                    "eval_type": r.eval_type,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "precision": float(r.precision) if r.precision else None,
                    "recall": float(r.recall) if r.recall else None,
                    "f1": float(r.f1_score) if r.f1_score else None,
                    "accuracy": float(r.accuracy) if r.accuracy else None,
                    "num_cases": r.num_test_cases,
                }
                for r in runs
            ]
        }
    finally:
        db.close()


def get_run_details(run_id: int) -> dict | None:
    """Get full details for a specific eval run.

    Args:
        run_id: Database ID of the eval run

    Returns:
        Full eval run data including detailed_results, or None if not found
    """
    from app.database import SessionLocal
    from app.models.eval_run import EvalRun

    db = SessionLocal()
    try:
        run = db.query(EvalRun).filter(EvalRun.id == run_id).first()
        if not run:
            return None

        return {
            "id": run.id,
            "model": run.model_name,
            "eval_type": run.eval_type,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "precision": float(run.precision) if run.precision else None,
            "recall": float(run.recall) if run.recall else None,
            "f1": float(run.f1_score) if run.f1_score else None,
            "accuracy": float(run.accuracy) if run.accuracy else None,
            "num_cases": run.num_test_cases,
            "test_data_source": run.test_data_source,
            "execution_time": float(run.execution_time_seconds)
            if run.execution_time_seconds
            else None,
            "notes": run.notes,
            "detailed_results": run.detailed_results,
        }
    finally:
        db.close()
