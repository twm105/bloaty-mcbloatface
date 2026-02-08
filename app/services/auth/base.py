"""Abstract base class for authentication providers."""
from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session as DBSession

from app.models.user import User


class AuthProvider(ABC):
    """
    Abstract authentication provider interface.

    This abstraction allows swapping between local password auth and
    external providers like Keycloak/OAuth without changing route code.
    """

    @abstractmethod
    async def authenticate(self, db: DBSession, email: str, password: str) -> Optional[User]:
        """
        Authenticate user with email and password.

        Returns User if credentials are valid, None otherwise.
        """
        pass

    @abstractmethod
    async def create_user(
        self,
        db: DBSession,
        email: str,
        password: str,
        is_admin: bool = False
    ) -> User:
        """
        Create a new user with the given credentials.

        Returns the created User.
        """
        pass

    @abstractmethod
    async def get_user_from_request(self, db: DBSession, request: Request) -> Optional[User]:
        """
        Extract and validate user from request (session cookie, OAuth token, etc).

        Returns User if authenticated, None otherwise.
        """
        pass

    @abstractmethod
    async def create_session(self, db: DBSession, user: User, request: Request) -> str:
        """
        Create a new session for the user.

        Returns the session token to be stored in cookie.
        """
        pass

    @abstractmethod
    async def revoke_session(self, db: DBSession, token: str) -> bool:
        """
        Revoke/invalidate a session by its token.

        Returns True if session was revoked, False if not found.
        """
        pass

    @abstractmethod
    async def revoke_all_sessions(self, db: DBSession, user_id: UUID, except_token: Optional[str] = None) -> int:
        """
        Revoke all sessions for a user, optionally excluding current session.

        Returns count of sessions revoked.
        """
        pass

    @abstractmethod
    async def change_password(
        self,
        db: DBSession,
        user: User,
        current_password: str,
        new_password: str
    ) -> bool:
        """
        Change user's password.

        Validates current password before changing.
        Returns True if successful, False if current password incorrect.
        """
        pass

    @abstractmethod
    async def reset_password(self, db: DBSession, user: User) -> str:
        """
        Reset user's password to a random temporary password.

        Admin function - does not require current password.
        Returns the new temporary password.
        """
        pass
