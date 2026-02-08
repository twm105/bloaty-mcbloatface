"""FastAPI dependencies for authentication."""
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services.auth import get_auth_provider


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """
    Get the currently authenticated user.

    Raises 401 if not authenticated (for API endpoints).
    For HTML pages, consider using require_auth_page instead.
    """
    auth_provider = get_auth_provider()
    user = await auth_provider.get_user_from_request(db, request)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    return user


async def get_optional_user(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Get the current user if authenticated, None otherwise.

    Use for pages that work differently for logged in vs logged out users.
    """
    auth_provider = get_auth_provider()
    return await auth_provider.get_user_from_request(db, request)


async def require_admin(
    user: User = Depends(get_current_user)
) -> User:
    """
    Require the current user to be an admin.

    Raises 403 if user is not an admin.
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user


class RequireAuthPage:
    """
    Dependency class for protecting HTML pages.

    Redirects to login page instead of raising 401.
    """

    def __init__(self, admin_required: bool = False):
        self.admin_required = admin_required

    async def __call__(
        self,
        request: Request,
        db: Session = Depends(get_db)
    ) -> User:
        auth_provider = get_auth_provider()
        user = await auth_provider.get_user_from_request(db, request)

        if not user:
            # Store the intended destination for redirect after login
            return_url = str(request.url.path)
            if request.url.query:
                return_url += f"?{request.url.query}"
            raise HTTPException(
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
                headers={"Location": f"/auth/login?next={return_url}"}
            )

        if self.admin_required and not user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )

        return user


# Pre-configured instances
require_auth_page = RequireAuthPage(admin_required=False)
require_admin_page = RequireAuthPage(admin_required=True)
