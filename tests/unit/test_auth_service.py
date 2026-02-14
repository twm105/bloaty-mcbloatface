"""
Unit tests for AuthService (LocalAuthProvider).

Tests authentication functionality including:
- Password hashing and verification
- Session management
- User creation
- Password changes
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import bcrypt

from sqlalchemy.orm import Session

from app.services.auth.local_provider import LocalAuthProvider, local_auth_provider
from app.models import User, Session as UserSession
from tests.factories import create_user, create_session


class TestPasswordHashing:
    """Tests for password hashing and verification."""

    def test_hash_password_returns_hash(self):
        """Test that password hashing returns a hash."""
        provider = LocalAuthProvider()

        hashed = provider._hash_password("test_password")

        assert hashed is not None
        assert hashed != "test_password"
        assert hashed.startswith("$2b$")  # bcrypt prefix

    def test_hash_password_is_unique(self):
        """Test that hashing same password twice gives different hashes."""
        provider = LocalAuthProvider()

        hash1 = provider._hash_password("same_password")
        hash2 = provider._hash_password("same_password")

        assert hash1 != hash2  # Different salts

    def test_verify_password_correct(self):
        """Test that correct password verifies."""
        provider = LocalAuthProvider()
        password = "correct_password"

        hashed = provider._hash_password(password)
        result = provider._verify_password(password, hashed)

        assert result is True

    def test_verify_password_incorrect(self):
        """Test that incorrect password fails verification."""
        provider = LocalAuthProvider()

        hashed = provider._hash_password("correct_password")
        result = provider._verify_password("wrong_password", hashed)

        assert result is False

    def test_verify_password_empty(self):
        """Test that empty password doesn't verify."""
        provider = LocalAuthProvider()

        hashed = provider._hash_password("some_password")
        result = provider._verify_password("", hashed)

        assert result is False


class TestSessionToken:
    """Tests for session token generation."""

    def test_generate_session_token_length(self):
        """Test that session tokens have proper length."""
        provider = LocalAuthProvider()

        token = provider._generate_session_token()

        # token_urlsafe(32) produces 43-character string
        assert len(token) >= 32

    def test_generate_session_token_unique(self):
        """Test that session tokens are unique."""
        provider = LocalAuthProvider()

        tokens = [provider._generate_session_token() for _ in range(100)]

        assert len(set(tokens)) == 100  # All unique


class TestTempPassword:
    """Tests for temporary password generation."""

    def test_generate_temp_password_default_length(self):
        """Test that temp passwords have default length."""
        provider = LocalAuthProvider()

        password = provider._generate_temp_password()

        assert len(password) == 12

    def test_generate_temp_password_custom_length(self):
        """Test that temp passwords can have custom length."""
        provider = LocalAuthProvider()

        password = provider._generate_temp_password(length=20)

        assert len(password) == 20

    def test_generate_temp_password_alphanumeric(self):
        """Test that temp passwords are alphanumeric."""
        provider = LocalAuthProvider()

        password = provider._generate_temp_password()

        assert password.isalnum()


class TestAuthentication:
    """Tests for user authentication."""

    @pytest.mark.asyncio
    async def test_authenticate_success(self, db: Session):
        """Test successful authentication."""
        provider = LocalAuthProvider()

        # Create user with known password
        user = create_user(db, email="test@example.com", password="secret123")

        result = await provider.authenticate(db, "test@example.com", "secret123")

        assert result is not None
        assert result.id == user.id

    @pytest.mark.asyncio
    async def test_authenticate_wrong_password(self, db: Session):
        """Test authentication with wrong password."""
        provider = LocalAuthProvider()
        create_user(db, email="test@example.com", password="secret123")

        result = await provider.authenticate(db, "test@example.com", "wrongpassword")

        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_nonexistent_user(self, db: Session):
        """Test authentication with non-existent user."""
        provider = LocalAuthProvider()

        result = await provider.authenticate(db, "nonexistent@example.com", "password")

        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_case_insensitive_email(self, db: Session):
        """Test that email comparison is case insensitive."""
        provider = LocalAuthProvider()
        create_user(db, email="Test@Example.com", password="secret123")

        result = await provider.authenticate(db, "test@example.com", "secret123")

        assert result is not None


class TestUserCreation:
    """Tests for user creation."""

    @pytest.mark.asyncio
    async def test_create_user_basic(self, db: Session):
        """Test basic user creation."""
        provider = LocalAuthProvider()

        user = await provider.create_user(
            db, "new@example.com", "password123"
        )

        assert user.id is not None
        assert user.email == "new@example.com"
        assert user.password_hash is not None
        assert user.is_admin is False

    @pytest.mark.asyncio
    async def test_create_user_admin(self, db: Session):
        """Test admin user creation."""
        provider = LocalAuthProvider()

        user = await provider.create_user(
            db, "admin@example.com", "password123",
            is_admin=True
        )

        assert user.is_admin is True

    @pytest.mark.asyncio
    async def test_create_user_lowercases_email(self, db: Session):
        """Test that email is lowercased."""
        provider = LocalAuthProvider()

        user = await provider.create_user(
            db, "Test@EXAMPLE.com", "password123"
        )

        assert user.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_create_user_hashes_password(self, db: Session):
        """Test that password is hashed."""
        provider = LocalAuthProvider()

        user = await provider.create_user(
            db, "test@example.com", "plainpassword"
        )

        assert user.password_hash != "plainpassword"
        assert user.password_hash.startswith("$2b$")


class TestSessionManagement:
    """Tests for session management."""

    @pytest.mark.asyncio
    async def test_create_session(self, db: Session):
        """Test session creation."""
        provider = LocalAuthProvider()
        user = create_user(db)
        request = create_mock_request()

        token = await provider.create_session(db, user, request)

        assert token is not None
        assert len(token) >= 32

        # Verify session in database
        session = db.query(UserSession).filter(
            UserSession.token == token
        ).first()
        assert session is not None
        assert session.user_id == user.id

    @pytest.mark.asyncio
    async def test_create_session_sets_expiry(self, db: Session):
        """Test that session expiry is set."""
        provider = LocalAuthProvider()
        user = create_user(db)
        request = create_mock_request()

        token = await provider.create_session(db, user, request)

        session = db.query(UserSession).filter(
            UserSession.token == token
        ).first()
        assert session.expires_at > datetime.now(timezone.utc)

    @pytest.mark.asyncio
    async def test_create_session_stores_metadata(self, db: Session):
        """Test that session stores request metadata."""
        provider = LocalAuthProvider()
        user = create_user(db)
        request = create_mock_request(
            user_agent="TestBrowser/1.0",
            client_ip="192.168.1.1"
        )

        token = await provider.create_session(db, user, request)

        session = db.query(UserSession).filter(
            UserSession.token == token
        ).first()
        assert session.user_agent == "TestBrowser/1.0"
        assert session.ip_address == "192.168.1.1"

    @pytest.mark.asyncio
    async def test_revoke_session(self, db: Session):
        """Test session revocation."""
        provider = LocalAuthProvider()
        user = create_user(db)
        session = create_session(db, user)

        result = await provider.revoke_session(db, session.token)

        assert result is True
        # Verify session is deleted
        assert db.query(UserSession).filter(
            UserSession.token == session.token
        ).first() is None

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_session(self, db: Session):
        """Test revoking non-existent session returns False."""
        provider = LocalAuthProvider()

        result = await provider.revoke_session(db, "nonexistent_token")

        assert result is False

    @pytest.mark.asyncio
    async def test_revoke_all_sessions(self, db: Session):
        """Test revoking all sessions for a user."""
        provider = LocalAuthProvider()
        user = create_user(db)

        # Create multiple sessions
        for _ in range(3):
            create_session(db, user)

        count = await provider.revoke_all_sessions(db, user.id)

        assert count == 3
        # Verify all sessions are deleted
        assert db.query(UserSession).filter(
            UserSession.user_id == user.id
        ).count() == 0

    @pytest.mark.asyncio
    async def test_revoke_all_sessions_except_current(self, db: Session):
        """Test revoking all sessions except current."""
        provider = LocalAuthProvider()
        user = create_user(db)

        # Create multiple sessions
        sessions = [create_session(db, user) for _ in range(3)]
        current_token = sessions[0].token

        count = await provider.revoke_all_sessions(
            db, user.id, except_token=current_token
        )

        assert count == 2
        # Current session should remain
        assert db.query(UserSession).filter(
            UserSession.token == current_token
        ).first() is not None


class TestGetUserFromRequest:
    """Tests for getting user from request."""

    @pytest.mark.asyncio
    async def test_get_user_from_valid_session(self, db: Session):
        """Test getting user from valid session cookie."""
        provider = LocalAuthProvider()
        user = create_user(db)
        session = create_session(db, user)

        request = create_mock_request(cookies={"bloaty_session": session.token})

        result = await provider.get_user_from_request(db, request)

        assert result is not None
        assert result.id == user.id

    @pytest.mark.asyncio
    async def test_get_user_from_expired_session(self, db: Session):
        """Test that expired sessions return None."""
        provider = LocalAuthProvider()
        user = create_user(db)
        session = create_session(
            db, user,
            expires_in=timedelta(days=-1)  # Already expired
        )

        request = create_mock_request(cookies={"bloaty_session": session.token})

        result = await provider.get_user_from_request(db, request)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_from_no_cookie(self, db: Session):
        """Test that missing cookie returns None."""
        provider = LocalAuthProvider()

        request = create_mock_request(cookies={})

        result = await provider.get_user_from_request(db, request)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_from_invalid_token(self, db: Session):
        """Test that invalid token returns None."""
        provider = LocalAuthProvider()

        request = create_mock_request(cookies={"bloaty_session": "invalid_token"})

        result = await provider.get_user_from_request(db, request)

        assert result is None


class TestPasswordChange:
    """Tests for password changes."""

    @pytest.mark.asyncio
    async def test_change_password_success(self, db: Session):
        """Test successful password change."""
        provider = LocalAuthProvider()
        user = create_user(db, password="old_password")

        result = await provider.change_password(
            db, user, "old_password", "new_password"
        )

        assert result is True

        # Verify new password works
        db.refresh(user)
        assert provider._verify_password("new_password", user.password_hash)

    @pytest.mark.asyncio
    async def test_change_password_wrong_current(self, db: Session):
        """Test password change with wrong current password."""
        provider = LocalAuthProvider()
        user = create_user(db, password="old_password")

        result = await provider.change_password(
            db, user, "wrong_password", "new_password"
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_change_password_no_hash(self, db: Session):
        """Test password change when user has no hash."""
        provider = LocalAuthProvider()

        # Create user without password hash
        user = User(email="nohash@example.com", password_hash=None)
        db.add(user)
        db.flush()

        result = await provider.change_password(
            db, user, "anything", "new_password"
        )

        assert result is False


class TestPasswordReset:
    """Tests for password reset."""

    @pytest.mark.asyncio
    async def test_reset_password(self, db: Session):
        """Test password reset."""
        provider = LocalAuthProvider()
        user = create_user(db, password="old_password")

        temp_password = await provider.reset_password(db, user)

        assert temp_password is not None
        assert len(temp_password) == 12

        # Verify temp password works
        db.refresh(user)
        assert provider._verify_password(temp_password, user.password_hash)


# Helper function to create mock request
def create_mock_request(
    cookies: dict = None,
    user_agent: str = "pytest-test-client",
    client_ip: str = "127.0.0.1"
):
    """Create a mock FastAPI request for testing."""
    request = MagicMock()

    # Use MagicMock for cookies so we can control get() behavior
    cookies_dict = cookies or {}
    mock_cookies = MagicMock()
    mock_cookies.get = lambda key, default=None: cookies_dict.get(key, default)
    request.cookies = mock_cookies

    # Use MagicMock for headers
    mock_headers = MagicMock()
    mock_headers.get = lambda key, default="": user_agent if key.lower() == "user-agent" else default
    request.headers = mock_headers

    request.client = MagicMock()
    request.client.host = client_ip

    return request
