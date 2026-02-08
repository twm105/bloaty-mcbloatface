"""API endpoints for symptom logging and management."""
from datetime import datetime
from typing import Optional, List, Dict, Any
import json
import logging

from fastapi import APIRouter, Depends, Request, Form, HTTPException, Query

logger = logging.getLogger(__name__)
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models.user import User
from app.services.symptom_service import symptom_service
from app.services.ai_service import ClaudeService
from app.models.user_settings import UserSettings
from app.services.auth.dependencies import get_current_user

router = APIRouter(prefix="/symptoms", tags=["symptoms"])
templates = Jinja2Templates(directory="app/templates")

# AI service instance
claude_service = ClaudeService()


# =============================================================================
# Request/Response Models
# =============================================================================

class SymptomTag(BaseModel):
    name: str
    severity: int

class ElaborateRequest(BaseModel):
    tags: List[SymptomTag]
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    user_notes: Optional[str] = None

class DetectEpisodeRequest(BaseModel):
    tags: List[SymptomTag]
    start_time: str

class DetectOngoingSymptomRequest(BaseModel):
    symptom_name: str
    symptom_severity: int
    current_time: Optional[str] = None  # ISO format, defaults to now


# =============================================================================
# New Tag-Based Endpoints
# =============================================================================

@router.get("/tags/common")
async def get_common_tags(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Get quick-add symptom tags for the user.

    Returns hybrid of recent + common tags, or defaults if no history.
    Logic:
    - Get 3 most recent + 3 most common tags
    - Deduplicate (if tag is both recent and common, only show once)
    - Fill remaining slots with next most recent tags
    - If < 6 total, use defaults to fill
    - Max 6 tags total

    Returns: {"tags": [{"name": "bloating", "count": 15, "avg_severity": 6.2}, ...]}
    """
    # Default tags for new users
    DEFAULTS = [
        {"name": "bloating", "avg_severity": 5.0},
        {"name": "nausea", "avg_severity": 5.0},
        {"name": "cramping", "avg_severity": 5.0},
        {"name": "heartburn", "avg_severity": 5.0},
        {"name": "stomach pain", "avg_severity": 5.0},
        {"name": "fatigue", "avg_severity": 5.0},
    ]

    # Get recent and common tags
    recent_tags = symptom_service.get_most_recent_symptom_tags(db, user.id, limit=6)
    common_tags = symptom_service.get_most_common_symptom_tags(db, user.id, limit=3)

    # If no tags exist, return defaults
    if not recent_tags and not common_tags:
        return {"tags": DEFAULTS}

    # Build hybrid list: 3 recent + 3 common, deduplicated
    tags_dict = {}

    # Add recent tags first (up to 3)
    for tag in recent_tags[:3]:
        tags_dict[tag["name"]] = {
            "name": tag["name"],
            "avg_severity": tag["avg_severity"],
            "is_recent": True
        }

    # Add common tags (up to 3)
    for tag in common_tags:
        if tag["name"] not in tags_dict:
            tags_dict[tag["name"]] = {
                "name": tag["name"],
                "count": tag["count"],
                "avg_severity": tag["avg_severity"]
            }

    # If we have < 6, fill with more recent tags
    if len(tags_dict) < 6:
        for tag in recent_tags[3:]:
            if len(tags_dict) >= 6:
                break
            if tag["name"] not in tags_dict:
                tags_dict[tag["name"]] = {
                    "name": tag["name"],
                    "avg_severity": tag["avg_severity"],
                    "is_recent": True
                }

    # If still < 6, fill with defaults
    result = list(tags_dict.values())
    if len(result) < 6:
        for default in DEFAULTS:
            if len(result) >= 6:
                break
            if default["name"] not in tags_dict:
                result.append(default)

    return {"tags": result[:6]}


@router.get("/tags/autocomplete")
async def autocomplete_tags(q: str = Query(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Autocomplete search for symptom tags.

    Query params:
        q: Search query string

    Returns: {"suggestions": ["bloating", "gas", "nausea", ...]}
    """
    suggestions = symptom_service.search_symptom_tags(db, user.id, q, limit=10)
    return {"suggestions": suggestions}


@router.post("/tags/elaborate")
async def elaborate_tags(request: ElaborateRequest):
    """
    Generate AI elaboration from symptom tags (non-streaming).

    Request body:
        {
            "tags": [{"name": "bloating", "severity": 7}, ...],
            "start_time": "2026-01-30T14:00:00",
            "end_time": "2026-01-30T16:00:00",
            "user_notes": "..."
        }

    Returns: {"elaboration": "...", "success": true}
    """
    try:
        # Parse timestamps
        start_time = None
        end_time = None

        if request.start_time:
            start_time = datetime.fromisoformat(request.start_time)

        if request.end_time:
            end_time = datetime.fromisoformat(request.end_time)

        # Convert Pydantic models to dicts
        tags_dict = [{"name": tag.name, "severity": tag.severity} for tag in request.tags]

        # Call AI service
        result = await claude_service.elaborate_symptom_tags(
            tags=tags_dict,
            start_time=start_time,
            end_time=end_time,
            user_notes=request.user_notes
        )

        return {
            "elaboration": result["elaboration"],
            "success": True
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI elaboration failed: {str(e)}")


@router.post("/tags/elaborate-stream")
async def elaborate_tags_stream(request: ElaborateRequest):
    """
    Stream AI elaboration text from symptom tags.

    Request body:
        {
            "tags": [{"name": "bloating", "severity": 7}, ...],
            "start_time": "2026-01-30T14:00:00",
            "end_time": "2026-01-30T16:00:00",
            "user_notes": "..."
        }

    Returns: Streaming text/plain response with AI-generated text
    """
    try:
        # Parse timestamps
        start_time = None
        end_time = None

        if request.start_time:
            start_time = datetime.fromisoformat(request.start_time)

        if request.end_time:
            end_time = datetime.fromisoformat(request.end_time)

        # Convert Pydantic models to dicts
        tags_dict = [{"name": tag.name, "severity": tag.severity} for tag in request.tags]

        # Generate streaming response
        async def generate():
            async for chunk in claude_service.elaborate_symptom_tags_streaming(
                tags=tags_dict,
                start_time=start_time,
                end_time=end_time,
                user_notes=request.user_notes
            ):
                yield chunk.encode('utf-8')

        return StreamingResponse(generate(), media_type='text/plain')

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI elaboration failed: {str(e)}")


@router.post("/detect-ongoing")
async def detect_ongoing_symptom(
    request: DetectOngoingSymptomRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Detect if a single symptom is ongoing from recent history (3-day window).

    Returns:
        {
            "potential_ongoing": {...} or null,
            "is_ongoing": bool,
            "confidence": float,
            "reasoning": str,
            "name_match": "exact" | "similar" | "different",
            "recommended_name": str  # If names differ, what system recommends
        }
    """
    try:
        current_time = datetime.fromisoformat(request.current_time) if request.current_time else datetime.utcnow()

        # Search for similar symptom by name (3-day window)
        previous_symptom = symptom_service.detect_ongoing_symptom_by_name(
            db=db,
            user_id=user.id,
            symptom_name=request.symptom_name,
            lookback_hours=72  # 3 days
        )

        if not previous_symptom:
            return {
                "potential_ongoing": None,
                "is_ongoing": False,
                "confidence": 0.0,
                "reasoning": "No similar symptom found in the past 3 days"
            }

        # AI analysis for nuanced determination
        previous_data = {
            "name": previous_symptom.tags[0]["name"] if previous_symptom.tags else request.symptom_name,
            "severity": previous_symptom.tags[0]["severity"] if previous_symptom.tags else 0,
            "start_time": previous_symptom.start_time or previous_symptom.timestamp,
            "end_time": previous_symptom.end_time
        }

        current_data = {
            "name": request.symptom_name,
            "severity": request.symptom_severity,
            "time": current_time
        }

        ai_result = await claude_service.detect_ongoing_symptom(
            previous_symptom=previous_data,
            current_symptom=current_data
        )

        # Determine name match type
        prev_name = previous_data["name"].lower()
        curr_name = request.symptom_name.lower()

        if prev_name == curr_name:
            name_match = "exact"
            recommended_name = prev_name
        else:
            name_match = "different"
            # Bias toward existing tag (previous symptom)
            recommended_name = previous_data["name"]

        return {
            "potential_ongoing": {
                "id": previous_symptom.id,
                "name": previous_data["name"],
                "severity": previous_data["severity"],
                "start_time": previous_symptom.start_time.isoformat() if previous_symptom.start_time else previous_symptom.timestamp.isoformat(),
                "end_time": previous_symptom.end_time.isoformat() if previous_symptom.end_time else None
            },
            "is_ongoing": ai_result["is_ongoing"],
            "confidence": ai_result["confidence"],
            "reasoning": ai_result["reasoning"],
            "name_match": name_match,
            "recommended_name": recommended_name
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ongoing detection failed: {str(e)}")


@router.post("/detect-episode")
async def detect_episode(request: DetectEpisodeRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Detect if current symptoms are continuation of recent episode.

    Request body:
        {
            "tags": [{"name": "bloating", "severity": 7}, ...],
            "start_time": "2026-01-30T17:00:00"
        }

    Returns:
        {
            "potential_episode": {...} or null,
            "is_continuation": bool,
            "confidence": float,
            "reasoning": str
        }
    """
    try:
        # Parse start time
        current_time = datetime.fromisoformat(request.start_time)

        # Convert Pydantic models to dicts
        tags_dict = [{"name": tag.name, "severity": tag.severity} for tag in request.tags]

        # Detect similar recent symptoms
        previous_symptom = symptom_service.detect_similar_recent_symptoms(
            db, user.id, tags_dict, lookback_hours=48
        )

        if not previous_symptom:
            return {
                "potential_episode": None,
                "is_continuation": False,
                "confidence": 0.0,
                "reasoning": "No similar recent symptoms found"
            }

        # Call AI service for nuanced analysis
        previous_data = {
            "tags": previous_symptom.tags,
            "start_time": previous_symptom.start_time or previous_symptom.timestamp,
            "end_time": previous_symptom.end_time,
            "notes": previous_symptom.notes
        }

        ai_result = await claude_service.detect_episode_continuation(
            current_tags=tags_dict,
            current_time=current_time,
            previous_symptom=previous_data
        )

        return {
            "potential_episode": {
                "id": previous_symptom.id,
                "tags": previous_symptom.tags,
                "start_time": previous_symptom.start_time.isoformat() if previous_symptom.start_time else previous_symptom.timestamp.isoformat(),
                "notes": previous_symptom.notes
            },
            "is_continuation": ai_result["is_continuation"],
            "confidence": ai_result["confidence"],
            "reasoning": ai_result["reasoning"]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Episode detection failed: {str(e)}")


@router.post("/create-tagged")
async def create_tagged_symptom(
    tags_json: str = Form(...),
    ai_generated_text: Optional[str] = Form(None),
    final_notes: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create symptom with tag-based schema (now supports per-symptom times).

    Form fields:
        tags_json: JSON string of [{"name": "bloating", "severity": 7, "start_time": "...", "end_time": "...", "episode_id": 123}, ...]
        ai_generated_text: Original unedited AI response (optional)
        final_notes: User-edited final text (optional, same as AI if not edited)

    Returns: Redirect to history with success message
    """
    try:
        # Parse tags JSON (now includes per-symptom times and episode_id)
        tags = json.loads(tags_json)

        # Convert empty strings to NULL
        ai_generated = ai_generated_text if ai_generated_text else None
        final = final_notes if final_notes else None

        # Create symptom (service method now handles per-symptom times)
        symptom = symptom_service.create_symptom_with_tags(
            db=db,
            user_id=user.id,
            tags=tags,
            ai_generated_text=ai_generated,
            final_notes=final
        )

        return RedirectResponse(
            url="/symptoms/history?success=true",
            status_code=303
        )

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid tags JSON format")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create symptom: {str(e)}")


# =============================================================================
# Legacy Endpoints (kept for backward compatibility)
# =============================================================================

@router.get("/log", response_class=HTMLResponse)
async def symptom_log_page(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Symptom logging page."""
    # Get user settings for AI elaboration preference
    user_settings = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
    ai_elaborate_default = user_settings.ai_elaborate_symptoms if user_settings else True

    return templates.TemplateResponse(
        "symptoms/log.html",
        {
            "request": request,
            "user": user,
            "ai_elaborate_default": ai_elaborate_default
        }
    )


@router.post("/create")
async def create_symptom(
    request: Request,
    description: str = Form(...),
    symptom_type: str = Form(...),
    severity: int = Form(...),
    notes: Optional[str] = Form(None),
    symptom_timestamp: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new symptom entry.

    Returns: Redirect to symptom history
    """
    # Parse timestamp
    timestamp = None
    if symptom_timestamp:
        try:
            timestamp = datetime.fromisoformat(symptom_timestamp)
        except ValueError:
            timestamp = datetime.utcnow()
    else:
        timestamp = datetime.utcnow()

    # Validate severity
    if not 1 <= severity <= 10:
        raise HTTPException(status_code=400, detail="Severity must be between 1 and 10")

    # Create symptom
    symptom = symptom_service.create_symptom(
        db=db,
        user_id=user.id,
        raw_description=description,
        structured_type=symptom_type,
        severity=severity,
        notes=notes,
        timestamp=timestamp
    )

    # Redirect to history with success message
    return RedirectResponse(
        url="/symptoms/history?success=true",
        status_code=303
    )


@router.get("/history", response_class=HTMLResponse)
async def symptom_history_page(
    request: Request,
    success: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Symptom history page."""
    symptoms = symptom_service.get_user_symptoms(db, user.id, limit=50)

    return templates.TemplateResponse(
        "symptoms/history.html",
        {
            "request": request,
            "user": user,
            "symptoms": symptoms,
            "success": success
        }
    )


@router.get("/{symptom_id}/edit", response_class=HTMLResponse)
async def edit_symptom_page(
    request: Request,
    symptom_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reuse log page for editing (same pattern as meals)."""
    symptom = symptom_service.get_symptom(db, symptom_id)
    if not symptom:
        raise HTTPException(status_code=404, detail="Symptom not found")

    # Verify ownership
    if symptom.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    return templates.TemplateResponse(
        "symptoms/log.html",
        {
            "request": request,
            "user": user,
            "editing": True,
            "symptom": symptom,
            "symptom_id": symptom_id
        }
    )


@router.put("/{symptom_id}")
async def update_symptom_tags(
    symptom_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update symptom with tag-based data."""
    from fastapi.responses import Response

    data = await request.json()

    symptom = symptom_service.get_symptom(db, symptom_id)
    if not symptom:
        raise HTTPException(status_code=404, detail="Symptom not found")

    # Verify ownership
    if symptom.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Update symptom
    symptom.tags = data.get('tags', [])
    symptom.notes = data.get('notes')

    # Parse timestamps if provided
    if data.get('start_time'):
        try:
            symptom.start_time = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass

    if data.get('end_time'):
        try:
            symptom.end_time = datetime.fromisoformat(data['end_time'].replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            pass

    db.commit()
    return Response(status_code=200)


@router.post("/{symptom_id}/update")
async def update_symptom(
    symptom_id: int,
    description: str = Form(...),
    symptom_type: str = Form(...),
    severity: int = Form(...),
    notes: Optional[str] = Form(None),
    symptom_timestamp: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a symptom."""
    # Verify ownership first
    existing = symptom_service.get_symptom(db, symptom_id)
    if existing and existing.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Parse timestamp
    timestamp = None
    if symptom_timestamp:
        try:
            timestamp = datetime.fromisoformat(symptom_timestamp)
        except ValueError:
            pass

    # Validate severity
    if not 1 <= severity <= 10:
        raise HTTPException(status_code=400, detail="Severity must be between 1 and 10")

    # Update symptom
    symptom = symptom_service.update_symptom(
        db=db,
        symptom_id=symptom_id,
        raw_description=description,
        structured_type=symptom_type,
        severity=severity,
        notes=notes,
        timestamp=timestamp
    )

    if not symptom:
        raise HTTPException(status_code=404, detail="Symptom not found")

    return RedirectResponse(url="/symptoms/history", status_code=303)


@router.get("/debug/count")
async def debug_symptom_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Debug endpoint to check symptom count."""
    from app.models.symptom import Symptom
    total = db.query(Symptom).count()
    for_user = db.query(Symptom).filter(Symptom.user_id == user.id).count()
    symptoms_direct = db.query(Symptom).filter(Symptom.user_id == user.id).all()
    symptoms_service = symptom_service.get_user_symptoms(db, user.id, limit=50)
    return {
        "total_symptoms": total,
        "user_symptoms": for_user,
        "user_id": str(user.id),
        "direct_query_count": len(symptoms_direct),
        "service_query_count": len(symptoms_service),
        "first_3_ids_direct": [s.id for s in symptoms_direct[:3]],
        "first_3_ids_service": [s.id for s in symptoms_service[:3]]
    }

@router.delete("/{symptom_id}")
async def delete_symptom(
    symptom_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a symptom."""
    # Verify ownership first
    symptom = symptom_service.get_symptom(db, symptom_id)
    if symptom and symptom.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    success = symptom_service.delete_symptom(db, symptom_id)
    if not success:
        raise HTTPException(status_code=404, detail="Symptom not found")

    # Return empty response - htmx will remove the element
    from fastapi.responses import Response
    return Response(status_code=200)
