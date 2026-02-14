"""Main application routes."""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.user_settings import UserSettings
from app.services.auth.dependencies import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Home page with main navigation options."""
    # Check if user has acknowledged disclaimer
    settings = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()

    disclaimer_acknowledged = settings.disclaimer_acknowledged if settings else False

    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "user": user,
            "disclaimer_acknowledged": disclaimer_acknowledged,
        },
    )


@router.get("/analysis", response_class=HTMLResponse)
async def analysis(request: Request, user: User = Depends(get_current_user)):
    """Analysis and patterns page."""
    return templates.TemplateResponse(
        "analysis.html", {"request": request, "user": user}
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings(request: Request, user: User = Depends(get_current_user)):
    """Settings page."""
    return templates.TemplateResponse(
        "settings.html", {"request": request, "user": user}
    )
