"""Authentication routes for login, logout, registration, and account management."""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.invite import Invite
from app.services.auth import get_auth_provider
from app.services.auth.dependencies import (
    get_current_user,
    get_optional_user,
    require_admin,
)


router = APIRouter(prefix="/auth", tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


# =============================================================================
# Login / Logout
# =============================================================================


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    next: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    user: Optional[User] = Depends(get_optional_user),
):
    """Login page. Redirects to home if already logged in."""
    if user:
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        "auth/login.html", {"request": request, "next": next, "error": error}
    )


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Process login form."""
    auth_provider = get_auth_provider()
    user = await auth_provider.authenticate(db, email, password)

    if not user:
        # Redirect back to login with error
        return RedirectResponse(url="/auth/login?error=invalid", status_code=303)

    # Create session and set cookie
    token = await auth_provider.create_session(db, user, request)

    # Redirect to next URL or home
    redirect_url = next if next and next.startswith("/") and not next.startswith("//") else "/"
    response = RedirectResponse(url=redirect_url, status_code=303)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
    )
    return response


@router.post("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    """Logout and clear session."""
    auth_provider = get_auth_provider()

    # Revoke session from database
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        await auth_provider.revoke_session(db, token)

    # Clear cookie and redirect to login
    response = RedirectResponse(url="/auth/login", status_code=303)
    response.delete_cookie(settings.session_cookie_name)
    return response


# =============================================================================
# Registration (Invite-Only)
# =============================================================================


@router.get("/register", response_class=HTMLResponse)
async def register_page(
    request: Request,
    invite: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Registration page. Requires valid invite token."""
    if user:
        return RedirectResponse(url="/", status_code=303)

    # Validate invite token
    invite_valid = False
    if invite:
        now = datetime.now(timezone.utc)
        invite_record = (
            db.query(Invite)
            .filter(
                Invite.token == invite,
                Invite.expires_at > now,
                Invite.used_at.is_(None),
            )
            .first()
        )
        invite_valid = invite_record is not None

    return templates.TemplateResponse(
        "auth/register.html",
        {
            "request": request,
            "invite": invite,
            "invite_valid": invite_valid,
            "error": error,
        },
    )


@router.post("/register")
async def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    invite: str = Form(...),
    db: Session = Depends(get_db),
):
    """Process registration with invite token."""
    # Validate passwords match
    if password != password_confirm:
        return RedirectResponse(
            url=f"/auth/register?invite={invite}&error=passwords_mismatch",
            status_code=303,
        )

    # Validate password strength (basic)
    if len(password) < 8:
        return RedirectResponse(
            url=f"/auth/register?invite={invite}&error=password_too_short",
            status_code=303,
        )

    # Validate invite token
    now = datetime.now(timezone.utc)
    invite_record = (
        db.query(Invite)
        .filter(
            Invite.token == invite, Invite.expires_at > now, Invite.used_at.is_(None)
        )
        .first()
    )

    if not invite_record:
        return RedirectResponse(
            url=f"/auth/register?invite={invite}&error=invalid_invite", status_code=303
        )

    # Check if email already exists
    existing_user = db.query(User).filter(User.email == email.lower()).first()
    if existing_user:
        return RedirectResponse(
            url=f"/auth/register?invite={invite}&error=email_exists", status_code=303
        )

    # Create user
    auth_provider = get_auth_provider()
    user = await auth_provider.create_user(db, email, password, is_admin=False)

    # Mark invite as used
    invite_record.used_at = now
    invite_record.used_by = user.id
    db.commit()

    # Create session and set cookie (auto-login)
    token = await auth_provider.create_session(db, user, request)

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
    )
    return response


# =============================================================================
# Account Management
# =============================================================================


@router.get("/account", response_class=HTMLResponse)
async def account_page(
    request: Request,
    success: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Account management page."""
    # Get user's active invites (for admins)
    invites = []
    if user.is_admin:
        now = datetime.now(timezone.utc)
        invites = (
            db.query(Invite)
            .filter(
                Invite.created_by == user.id,
                Invite.expires_at > now,
                Invite.used_at.is_(None),
            )
            .order_by(Invite.created_at.desc())
            .all()
        )

    # Get all users (for admins)
    all_users = []
    if user.is_admin:
        all_users = db.query(User).order_by(User.created_at.desc()).all()

    return templates.TemplateResponse(
        "auth/account.html",
        {
            "request": request,
            "user": user,
            "invites": invites,
            "all_users": all_users,
            "success": success,
            "error": error,
        },
    )


@router.post("/change-password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    new_password_confirm: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change user's own password."""
    # Validate new passwords match
    if new_password != new_password_confirm:
        return RedirectResponse(
            url="/auth/account?error=passwords_mismatch", status_code=303
        )

    # Validate password strength
    if len(new_password) < 8:
        return RedirectResponse(
            url="/auth/account?error=password_too_short", status_code=303
        )

    # Change password
    auth_provider = get_auth_provider()
    success = await auth_provider.change_password(
        db, user, current_password, new_password
    )

    if not success:
        return RedirectResponse(
            url="/auth/account?error=wrong_password", status_code=303
        )

    return RedirectResponse(
        url="/auth/account?success=password_changed", status_code=303
    )


# =============================================================================
# Invite Management (Admin Only)
# =============================================================================


@router.post("/invite")
async def create_invite(
    request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)
):
    """Generate a new invite link (admin only)."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    invite = Invite(token=token, created_by=user.id, expires_at=expires_at)
    db.add(invite)
    db.commit()

    # Return the invite URL
    base_url = str(request.base_url).rstrip("/")
    invite_url = f"{base_url}/auth/register?invite={token}"

    return {"invite_url": invite_url, "expires_at": expires_at.isoformat()}


@router.get("/invites")
async def list_invites(
    user: User = Depends(require_admin), db: Session = Depends(get_db)
):
    """List active invites (admin only)."""
    now = datetime.now(timezone.utc)
    invites = (
        db.query(Invite)
        .filter(
            Invite.created_by == user.id,
            Invite.expires_at > now,
            Invite.used_at.is_(None),
        )
        .order_by(Invite.created_at.desc())
        .all()
    )

    return {
        "invites": [
            {
                "id": inv.id,
                "token": inv.token,
                "created_at": inv.created_at.isoformat(),
                "expires_at": inv.expires_at.isoformat(),
            }
            for inv in invites
        ]
    }


@router.delete("/invite/{invite_id}")
async def revoke_invite(
    invite_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)
):
    """Revoke an invite (admin only)."""
    invite = (
        db.query(Invite)
        .filter(Invite.id == invite_id, Invite.created_by == user.id)
        .first()
    )

    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")

    db.delete(invite)
    db.commit()

    return Response(status_code=200)


# =============================================================================
# Admin User Management
# =============================================================================


@router.post("/reset-password/{user_id}")
async def reset_user_password(
    user_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    """Reset a user's password (admin only). Returns temporary password."""
    from uuid import UUID

    try:
        target_user_id = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    target_user = db.query(User).filter(User.id == target_user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    auth_provider = get_auth_provider()
    temp_password = await auth_provider.reset_password(db, target_user)

    return {"temp_password": temp_password}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    """Delete a user and all their data (admin only)."""
    from uuid import UUID

    try:
        target_user_id = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    # Prevent self-deletion
    if target_user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    target_user = db.query(User).filter(User.id == target_user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(target_user)
    db.commit()

    return {"success": True}
