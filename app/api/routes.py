"""Main application routes."""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user_settings import UserSettings
import uuid

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# MVP single-user ID
MVP_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    """Home page with main navigation options."""
    # Check if user has acknowledged disclaimer
    settings = db.query(UserSettings).filter(
        UserSettings.user_id == MVP_USER_ID
    ).first()

    disclaimer_acknowledged = settings.disclaimer_acknowledged if settings else False

    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "disclaimer_acknowledged": disclaimer_acknowledged
        }
    )


@router.get("/symptoms/log", response_class=HTMLResponse)
async def symptom_log(request: Request):
    """Symptom logging page."""
    return templates.TemplateResponse("symptoms/log.html", {"request": request})


@router.get("/symptoms/history", response_class=HTMLResponse)
async def symptom_history(request: Request):
    """Symptom history page."""
    return templates.TemplateResponse("symptoms/history.html", {"request": request})


@router.get("/analysis", response_class=HTMLResponse)
async def analysis(request: Request):
    """Analysis and patterns page."""
    return templates.TemplateResponse("analysis.html", {"request": request})


@router.get("/settings", response_class=HTMLResponse)
async def settings(request: Request):
    """Settings page."""
    return templates.TemplateResponse("settings.html", {"request": request})
