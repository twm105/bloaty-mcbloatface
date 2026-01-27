"""API endpoints for symptom logging and management."""
from datetime import datetime
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.symptom_service import symptom_service

router = APIRouter(prefix="/symptoms", tags=["symptoms"])
templates = Jinja2Templates(directory="app/templates")

# MVP single-user ID
MVP_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


@router.get("/log", response_class=HTMLResponse)
async def symptom_log_page(request: Request):
    """Symptom logging page."""
    symptom_types = symptom_service.get_common_symptom_types()
    return templates.TemplateResponse(
        "symptoms/log.html",
        {
            "request": request,
            "symptom_types": symptom_types
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
        user_id=MVP_USER_ID,
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
    db: Session = Depends(get_db)
):
    """Symptom history page."""
    symptoms = symptom_service.get_user_symptoms(db, MVP_USER_ID, limit=50)

    return templates.TemplateResponse(
        "symptoms/history.html",
        {
            "request": request,
            "symptoms": symptoms,
            "success": success
        }
    )


@router.get("/{symptom_id}/edit", response_class=HTMLResponse)
async def edit_symptom_page(
    request: Request,
    symptom_id: int,
    db: Session = Depends(get_db)
):
    """Edit symptom page."""
    symptom = symptom_service.get_symptom(db, symptom_id)
    if not symptom:
        raise HTTPException(status_code=404, detail="Symptom not found")

    symptom_types = symptom_service.get_common_symptom_types()

    return templates.TemplateResponse(
        "symptoms/edit.html",
        {
            "request": request,
            "symptom": symptom,
            "symptom_types": symptom_types
        }
    )


@router.post("/{symptom_id}/update")
async def update_symptom(
    symptom_id: int,
    description: str = Form(...),
    symptom_type: str = Form(...),
    severity: int = Form(...),
    notes: Optional[str] = Form(None),
    symptom_timestamp: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Update a symptom."""
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


@router.delete("/{symptom_id}")
async def delete_symptom(
    symptom_id: int,
    db: Session = Depends(get_db)
):
    """Delete a symptom."""
    success = symptom_service.delete_symptom(db, symptom_id)
    if not success:
        raise HTTPException(status_code=404, detail="Symptom not found")

    return {"status": "deleted"}
