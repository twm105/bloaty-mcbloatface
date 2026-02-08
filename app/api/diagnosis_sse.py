"""
SSE streaming endpoint for real-time diagnosis progress updates.
"""
import json
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DiagnosisRun
from app.models.user import User
from app.services.sse_publisher import SSESubscriber
from app.services.auth.dependencies import get_current_user

router = APIRouter(prefix="/diagnosis", tags=["diagnosis-sse"])


@router.get("/stream/{run_id}")
async def stream_diagnosis_progress(
    run_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Stream diagnosis progress updates via Server-Sent Events.

    Events:
    - progress: {"completed": N, "total": M, "ingredient": "name"}
    - result: {full DiagnosisResult JSON}
    - complete: {"run_id": N, "total_results": M}
    - error: {"message": "..."}

    Args:
        run_id: DiagnosisRun ID to stream updates for

    Returns:
        EventSourceResponse with SSE stream
    """
    # Verify run exists and belongs to user
    diagnosis_run = db.query(DiagnosisRun).filter(DiagnosisRun.id == run_id).first()
    if not diagnosis_run:
        raise HTTPException(status_code=404, detail="Diagnosis run not found")

    if diagnosis_run.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # If already completed, return final state immediately
    if diagnosis_run.status == "completed":
        async def completed_generator():
            yield {
                "event": "complete",
                "data": json.dumps({
                    "run_id": run_id,
                    "total_results": len(diagnosis_run.results) if diagnosis_run.results else 0
                })
            }
        return EventSourceResponse(completed_generator())

    # If failed, return error immediately
    if diagnosis_run.status == "failed":
        async def failed_generator():
            yield {
                "event": "error",
                "data": json.dumps({
                    "message": diagnosis_run.error_message or "Analysis failed"
                })
            }
        return EventSourceResponse(failed_generator())

    # Stream events from Redis pub/sub
    async def event_generator():
        subscriber = SSESubscriber(run_id)
        try:
            # Send initial state
            yield {
                "event": "progress",
                "data": json.dumps({
                    "completed": diagnosis_run.completed_ingredients or 0,
                    "total": diagnosis_run.total_ingredients or 0,
                    "ingredient": ""
                })
            }

            # Listen for events
            async for event_type, data in subscriber.listen():
                yield {
                    "event": event_type,
                    "data": json.dumps(data)
                }

                # Stop on complete or error
                if event_type in ("complete", "error"):
                    break

        except asyncio.CancelledError:
            # Client disconnected
            pass
        finally:
            subscriber.close()

    return EventSourceResponse(event_generator())


@router.get("/status/{run_id}")
async def get_diagnosis_status(
    run_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current status of a diagnosis run (non-streaming).

    Args:
        run_id: DiagnosisRun ID

    Returns:
        JSON with status info
    """
    diagnosis_run = db.query(DiagnosisRun).filter(DiagnosisRun.id == run_id).first()
    if not diagnosis_run:
        raise HTTPException(status_code=404, detail="Diagnosis run not found")

    if diagnosis_run.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    return {
        "run_id": diagnosis_run.id,
        "status": diagnosis_run.status,
        "total_ingredients": diagnosis_run.total_ingredients,
        "completed_ingredients": diagnosis_run.completed_ingredients,
        "started_at": diagnosis_run.started_at.isoformat() if diagnosis_run.started_at else None,
        "completed_at": diagnosis_run.completed_at.isoformat() if diagnosis_run.completed_at else None,
        "error_message": diagnosis_run.error_message,
        "results_count": len(diagnosis_run.results) if diagnosis_run.results else 0
    }
