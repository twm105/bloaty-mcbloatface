"""Admin dashboard routes for platform usage metrics."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services.admin_dashboard_service import (
    backfill_orphaned_usage_logs,
    get_all_users_overview,
    get_platform_totals,
    get_user_detail,
)
from app.services.auth.dependencies import require_admin

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin overview dashboard with all users and platform stats."""
    backfill_orphaned_usage_logs(db)
    overview, week_labels = get_all_users_overview(db)
    totals = get_platform_totals(db)

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "user": user,
            "overview": overview,
            "week_labels": week_labels,
            "totals": totals,
        },
    )


@router.get("/dashboard/user/{user_id}", response_class=HTMLResponse)
async def user_detail(
    request: Request,
    user_id: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Detailed usage dashboard for a single user."""
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    detail = get_user_detail(db, uid)
    if not detail:
        raise HTTPException(status_code=404, detail="User not found")

    return templates.TemplateResponse(
        "admin/user_detail.html",
        {
            "request": request,
            "user": user,
            "detail": detail,
        },
    )
