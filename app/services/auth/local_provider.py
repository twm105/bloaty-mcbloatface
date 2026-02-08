"""Local password-based authentication provider."""
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import bcrypt
from fastapi import Request
from sqlalchemy.orm import Session as DBSession

from app.config import settings
from app.models.user import User
from app.models.session import Session
from app.services.auth.base import AuthProvider


class LocalAuthProvider(AuthProvider):
    """
    Local authentication provider using password hashing and database sessions.

    Passwords are hashed with bcrypt. Sessions are stored in database with
    secure random tokens.
    """

    def _hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

    def _generate_session_token(self) -> str:
        """Generate a cryptographically secure session token."""
        return secrets.token_urlsafe(32)

    def _generate_temp_password(self, length: int = 12) -> str:
        """Generate a random temporary password."""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    async def authenticate(self, db: DBSession, email: str, password: str) -> Optional[User]:
        """Authenticate user with email and password."""
        user = db.query(User).filter(User.email == email.lower()).first()
        if not user or not user.password_hash:
            return None
        if not self._verify_password(password, user.password_hash):
            return None
        return user

    async def create_user(
        self,
        db: DBSession,
        email: str,
        password: str,
        is_admin: bool = False
    ) -> User:
        """Create a new user with hashed password."""
        user = User(
            email=email.lower(),
            password_hash=self._hash_password(password),
            is_admin=is_admin
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    async def get_user_from_request(self, db: DBSession, request: Request) -> Optional[User]:
        """Extract user from session cookie."""
        token = request.cookies.get(settings.session_cookie_name)
        if not token:
            return None

        # Find valid session
        now = datetime.now(timezone.utc)
        session = db.query(Session).filter(
            Session.token == token,
            Session.expires_at > now
        ).first()

        if not session:
            return None

        return session.user

    async def create_session(self, db: DBSession, user: User, request: Request) -> str:
        """Create a new session for the user."""
        token = self._generate_session_token()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.session_max_age)

        # Extract request metadata
        user_agent = request.headers.get("user-agent", "")[:512]
        client_ip = request.client.host if request.client else None

        session = Session(
            user_id=user.id,
            token=token,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=client_ip
        )
        db.add(session)
        db.commit()

        return token

    async def revoke_session(self, db: DBSession, token: str) -> bool:
        """Revoke a session by its token."""
        session = db.query(Session).filter(Session.token == token).first()
        if not session:
            return False
        db.delete(session)
        db.commit()
        return True

    async def revoke_all_sessions(
        self,
        db: DBSession,
        user_id: UUID,
        except_token: Optional[str] = None
    ) -> int:
        """Revoke all sessions for a user."""
        query = db.query(Session).filter(Session.user_id == user_id)
        if except_token:
            query = query.filter(Session.token != except_token)
        count = query.count()
        query.delete()
        db.commit()
        return count

    async def change_password(
        self,
        db: DBSession,
        user: User,
        current_password: str,
        new_password: str
    ) -> bool:
        """Change user's password after verifying current password."""
        if not user.password_hash:
            return False
        if not self._verify_password(current_password, user.password_hash):
            return False
        user.password_hash = self._hash_password(new_password)
        db.commit()
        return True

    async def reset_password(self, db: DBSession, user: User) -> str:
        """Reset user's password to a random temporary password."""
        temp_password = self._generate_temp_password()
        user.password_hash = self._hash_password(temp_password)
        db.commit()
        return temp_password


# Singleton instance
local_auth_provider = LocalAuthProvider()
