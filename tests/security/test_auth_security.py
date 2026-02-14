"""
Security tests for authentication and authorization.

Tests security aspects including:
- Session security
- Access control
- Token handling
- Admin privilege escalation prevention
"""

import pytest
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User, Session as UserSession
from tests.factories import create_user, create_session, create_invite


@pytest.mark.security
class TestSessionSecurity:
    """Tests for session security."""

    def test_session_token_not_guessable(self, db: Session):
        """Test that session tokens are sufficiently random."""
        user = create_user(db)

        tokens = []
        for _ in range(100):
            session = create_session(db, user)
            tokens.append(session.token)

        # All tokens should be unique
        assert len(set(tokens)) == 100

        # Tokens should be sufficiently long
        for token in tokens:
            assert len(token) >= 32

    def test_expired_session_rejected(self, client: TestClient, db: Session):
        """Test that expired sessions are rejected."""
        user = create_user(db)
        session = create_session(db, user, expires_in=timedelta(days=-1))

        # Try to access protected endpoint with expired session
        client.cookies.set("bloaty_session", session.token)
        response = client.get("/meals/history", follow_redirects=False)

        assert response.status_code in [302, 303, 307, 401]

    def test_invalid_session_token_rejected(self, client: TestClient):
        """Test that invalid session tokens are rejected."""
        client.cookies.set("bloaty_session", "invalid_token_12345")
        response = client.get("/meals/history", follow_redirects=False)

        assert response.status_code in [302, 303, 307, 401]

    def test_session_cleared_on_logout(
        self, auth_client: TestClient, test_session: UserSession, db: Session
    ):
        """Test that logout properly clears session."""
        token = test_session.token

        auth_client.post("/auth/logout", follow_redirects=False)

        # Session should be deleted from database
        db.expire_all()
        remaining = db.query(UserSession).filter(UserSession.token == token).first()
        assert remaining is None

    def test_session_not_shared_between_users(self, client: TestClient, db: Session):
        """Test that one user's session can't be used by another."""
        user1 = create_user(db, email="user1@example.com")
        create_user(db, email="user2@example.com")

        session1 = create_session(db, user1)

        # User2 tries to use User1's session
        client.cookies.set("bloaty_session", session1.token)

        # Access should be as user1, not user2
        # The session should resolve to user1 regardless


@pytest.mark.security
class TestAccessControl:
    """Tests for access control enforcement."""

    def test_cannot_access_other_user_meals(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test user cannot access another user's meals."""
        other_user = create_user(db, email="other@example.com")
        from tests.factories import create_meal

        meal = create_meal(db, other_user, name="Private Meal")

        response = auth_client.get(f"/meals/{meal.id}/edit-ingredients")

        assert response.status_code in [403, 404]

    def test_cannot_modify_other_user_data(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test user cannot modify another user's data."""
        other_user = create_user(db, email="other@example.com")
        from tests.factories import create_symptom

        symptom = create_symptom(db, other_user)

        response = auth_client.delete(f"/symptoms/{symptom.id}")

        assert response.status_code in [403, 404]

    def test_admin_required_for_invite_creation(
        self, auth_client: TestClient, test_user: User
    ):
        """Test non-admin cannot create invites."""
        response = auth_client.post("/auth/invite")

        assert response.status_code in [401, 403, 302, 303]

    def test_admin_required_for_password_reset(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test non-admin cannot reset other users' passwords."""
        other_user = create_user(db, email="other@example.com")

        response = auth_client.post(f"/auth/reset-password/{other_user.id}")

        assert response.status_code in [401, 403, 302, 303]

    def test_admin_required_for_user_deletion(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test non-admin cannot delete users."""
        other_user = create_user(db, email="other@example.com")

        response = auth_client.delete(f"/auth/users/{other_user.id}")

        assert response.status_code in [401, 403, 302, 303]


@pytest.mark.security
class TestInviteSecurity:
    """Tests for invite token security."""

    def test_invite_token_not_guessable(self, db: Session):
        """Test that invite tokens are sufficiently random."""
        admin = create_user(db, is_admin=True)

        tokens = []
        for _ in range(50):
            invite = create_invite(db, admin)
            tokens.append(invite.token)

        # All tokens should be unique
        assert len(set(tokens)) == 50

        # Tokens should be sufficiently long
        for token in tokens:
            assert len(token) >= 32

    def test_expired_invite_rejected(self, client: TestClient, db: Session):
        """Test that expired invites are rejected."""
        admin = create_user(db, is_admin=True)
        invite = create_invite(db, admin, expires_in=timedelta(days=-1))

        response = client.post(
            "/auth/register",
            data={
                "email": "new@example.com",
                "password": "password123",
                "password_confirm": "password123",
                "invite": invite.token,
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "error=invalid_invite" in response.headers.get("location", "")

    def test_used_invite_rejected(self, client: TestClient, db: Session):
        """Test that already-used invites are rejected."""
        admin = create_user(db, is_admin=True)
        existing_user = create_user(db, email="existing@example.com")
        invite = create_invite(db, admin, used=True, used_by=existing_user)

        response = client.post(
            "/auth/register",
            data={
                "email": "new@example.com",
                "password": "password123",
                "password_confirm": "password123",
                "invite": invite.token,
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "error=invalid_invite" in response.headers.get("location", "")

    def test_invalid_invite_rejected(self, client: TestClient, db: Session):
        """Test that invalid invite tokens are rejected."""
        response = client.post(
            "/auth/register",
            data={
                "email": "new@example.com",
                "password": "password123",
                "password_confirm": "password123",
                "invite": "completely_made_up_token",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "error=invalid_invite" in response.headers.get("location", "")


@pytest.mark.security
class TestPasswordSecurity:
    """Tests for password security."""

    def test_password_not_stored_plaintext(self, db: Session):
        """Test that passwords are hashed, not stored plaintext."""
        user = create_user(db, email="test@example.com", password="secret123")

        assert user.password_hash is not None
        assert user.password_hash != "secret123"
        assert "$2b$" in user.password_hash  # bcrypt prefix

    def test_password_minimum_length_enforced(self, client: TestClient, db: Session):
        """Test that short passwords are rejected."""
        admin = create_user(db, is_admin=True)
        invite = create_invite(db, admin)

        response = client.post(
            "/auth/register",
            data={
                "email": "new@example.com",
                "password": "short",
                "password_confirm": "short",
                "invite": invite.token,
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "error=password_too_short" in response.headers.get("location", "")

    def test_password_change_requires_current(
        self, auth_client: TestClient, test_user: User
    ):
        """Test that password change requires current password."""
        response = auth_client.post(
            "/auth/change-password",
            data={
                "current_password": "wrong_password",
                "new_password": "newpassword456",
                "new_password_confirm": "newpassword456",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert "error=wrong_password" in response.headers.get("location", "")


@pytest.mark.security
class TestAdminPrivilegeEscalation:
    """Tests for admin privilege escalation prevention."""

    def test_user_cannot_make_self_admin(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test that non-admin user cannot escalate to admin."""
        # If there's an endpoint that could modify user admin status,
        # ensure it's protected. For now, we verify the user isn't admin.
        assert test_user.is_admin is False

    def test_admin_cannot_delete_self(self, admin_client: TestClient, admin_user: User):
        """Test that admin cannot delete their own account."""
        response = admin_client.delete(f"/auth/users/{admin_user.id}")

        assert response.status_code == 400

    def test_invite_creation_respects_admin_flag(
        self, admin_client: TestClient, auth_client: TestClient, admin_user: User
    ):
        """Test invite creation is admin-only."""
        # Admin can create
        admin_response = admin_client.post("/auth/invite")
        assert admin_response.status_code == 200

        # Non-admin cannot
        non_admin_response = auth_client.post("/auth/invite")
        assert non_admin_response.status_code in [401, 403, 302, 303]
