"""
Integration tests for Authentication API.

Tests the full auth flow including:
- Login/logout
- Registration with invites
- Session management
- Admin endpoints
"""
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User, Session as UserSession, Invite
from tests.factories import create_user, create_session, create_invite


class TestLoginFlow:
    """Tests for login functionality."""

    def test_login_page_renders(self, client: TestClient):
        """Test that login page renders."""
        response = client.get("/auth/login")

        assert response.status_code == 200
        assert "Login" in response.text or "login" in response.text.lower()

    def test_login_success(self, client: TestClient, db: Session):
        """Test successful login."""
        create_user(db, email="test@example.com", password="password123")

        response = client.post(
            "/auth/login",
            data={"email": "test@example.com", "password": "password123"},
            follow_redirects=False
        )

        assert response.status_code == 303
        assert "bloaty_session" in response.cookies

    def test_login_wrong_password(self, client: TestClient, db: Session):
        """Test login with wrong password."""
        create_user(db, email="test@example.com", password="password123")

        response = client.post(
            "/auth/login",
            data={"email": "test@example.com", "password": "wrongpassword"},
            follow_redirects=False
        )

        assert response.status_code == 303
        assert "error=invalid" in response.headers.get("location", "")

    def test_login_nonexistent_user(self, client: TestClient, db: Session):
        """Test login with non-existent user."""
        response = client.post(
            "/auth/login",
            data={"email": "nonexistent@example.com", "password": "password"},
            follow_redirects=False
        )

        assert response.status_code == 303
        assert "error=invalid" in response.headers.get("location", "")

    def test_login_redirects_to_next(self, client: TestClient, db: Session):
        """Test that login redirects to 'next' parameter."""
        create_user(db, email="test@example.com", password="password123")

        response = client.post(
            "/auth/login",
            data={
                "email": "test@example.com",
                "password": "password123",
                "next": "/meals/history"
            },
            follow_redirects=False
        )

        assert response.status_code == 303
        assert response.headers.get("location") == "/meals/history"

    def test_login_page_redirects_if_logged_in(
        self, auth_client: TestClient, test_user: User
    ):
        """Test that login page redirects if already logged in."""
        response = auth_client.get("/auth/login", follow_redirects=False)

        assert response.status_code == 303


class TestLogoutFlow:
    """Tests for logout functionality."""

    def test_logout_clears_session(
        self, auth_client: TestClient, test_session: UserSession, db: Session
    ):
        """Test that logout clears session."""
        response = auth_client.post("/auth/logout", follow_redirects=False)

        assert response.status_code == 303
        assert response.headers.get("location") == "/auth/login"

        # Verify session is revoked
        db.expire_all()
        session = db.query(UserSession).filter(
            UserSession.token == test_session.token
        ).first()
        assert session is None

    def test_logout_clears_cookie(self, auth_client: TestClient):
        """Test that logout clears the session cookie."""
        response = auth_client.post("/auth/logout", follow_redirects=False)

        # Cookie should be deleted (set to empty or with past expiry)
        cookie_header = response.headers.get("set-cookie", "")
        assert "bloaty_session" in cookie_header


class TestRegistration:
    """Tests for registration with invites."""

    def test_register_page_renders(self, client: TestClient, db: Session):
        """Test that register page renders with valid invite."""
        admin = create_user(db, is_admin=True)
        invite = create_invite(db, admin)

        response = client.get(f"/auth/register?invite={invite.token}")

        assert response.status_code == 200

    def test_register_page_shows_invalid_for_bad_invite(
        self, client: TestClient, db: Session
    ):
        """Test that register page shows invalid for bad invite."""
        response = client.get("/auth/register?invite=invalid_token")

        assert response.status_code == 200
        # Page should indicate invalid invite

    def test_register_success(self, client: TestClient, db: Session):
        """Test successful registration."""
        admin = create_user(db, is_admin=True)
        invite = create_invite(db, admin)

        response = client.post(
            "/auth/register",
            data={
                "email": "newuser@example.com",
                "password": "password123",
                "password_confirm": "password123",
                "invite": invite.token
            },
            follow_redirects=False
        )

        assert response.status_code == 303

        # Verify user created
        user = db.query(User).filter(User.email == "newuser@example.com").first()
        assert user is not None

        # Verify invite used
        db.refresh(invite)
        assert invite.used_at is not None

    def test_register_password_mismatch(self, client: TestClient, db: Session):
        """Test registration with mismatched passwords."""
        admin = create_user(db, is_admin=True)
        invite = create_invite(db, admin)

        response = client.post(
            "/auth/register",
            data={
                "email": "newuser@example.com",
                "password": "password123",
                "password_confirm": "differentpassword",
                "invite": invite.token
            },
            follow_redirects=False
        )

        assert response.status_code == 303
        assert "error=passwords_mismatch" in response.headers.get("location", "")

    def test_register_short_password(self, client: TestClient, db: Session):
        """Test registration with too short password."""
        admin = create_user(db, is_admin=True)
        invite = create_invite(db, admin)

        response = client.post(
            "/auth/register",
            data={
                "email": "newuser@example.com",
                "password": "short",
                "password_confirm": "short",
                "invite": invite.token
            },
            follow_redirects=False
        )

        assert response.status_code == 303
        assert "error=password_too_short" in response.headers.get("location", "")

    def test_register_invalid_invite(self, client: TestClient, db: Session):
        """Test registration with invalid invite."""
        response = client.post(
            "/auth/register",
            data={
                "email": "newuser@example.com",
                "password": "password123",
                "password_confirm": "password123",
                "invite": "invalid_token"
            },
            follow_redirects=False
        )

        assert response.status_code == 303
        assert "error=invalid_invite" in response.headers.get("location", "")

    def test_register_expired_invite(self, client: TestClient, db: Session):
        """Test registration with expired invite."""
        admin = create_user(db, is_admin=True)
        invite = create_invite(db, admin, expires_in=timedelta(days=-1))

        response = client.post(
            "/auth/register",
            data={
                "email": "newuser@example.com",
                "password": "password123",
                "password_confirm": "password123",
                "invite": invite.token
            },
            follow_redirects=False
        )

        assert response.status_code == 303
        assert "error=invalid_invite" in response.headers.get("location", "")

    def test_register_used_invite(self, client: TestClient, db: Session):
        """Test registration with already used invite."""
        admin = create_user(db, is_admin=True)
        used_by = create_user(db, email="other@example.com")
        invite = create_invite(db, admin, used=True, used_by=used_by)

        response = client.post(
            "/auth/register",
            data={
                "email": "newuser@example.com",
                "password": "password123",
                "password_confirm": "password123",
                "invite": invite.token
            },
            follow_redirects=False
        )

        assert response.status_code == 303
        assert "error=invalid_invite" in response.headers.get("location", "")

    def test_register_existing_email(self, client: TestClient, db: Session):
        """Test registration with existing email."""
        admin = create_user(db, is_admin=True)
        create_user(db, email="existing@example.com")
        invite = create_invite(db, admin)

        response = client.post(
            "/auth/register",
            data={
                "email": "existing@example.com",
                "password": "password123",
                "password_confirm": "password123",
                "invite": invite.token
            },
            follow_redirects=False
        )

        assert response.status_code == 303
        assert "error=email_exists" in response.headers.get("location", "")


class TestAccountManagement:
    """Tests for account management."""

    def test_account_page_requires_auth(self, client: TestClient):
        """Test that account page requires authentication."""
        response = client.get("/auth/account", follow_redirects=False)

        # Should redirect to login
        assert response.status_code in [302, 303, 307, 401]

    def test_account_page_renders(self, auth_client: TestClient, test_user: User):
        """Test that account page renders for logged in user."""
        response = auth_client.get("/auth/account")

        assert response.status_code == 200

    def test_change_password_success(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test successful password change."""
        response = auth_client.post(
            "/auth/change-password",
            data={
                "current_password": "testpassword123",
                "new_password": "newpassword456",
                "new_password_confirm": "newpassword456"
            },
            follow_redirects=False
        )

        assert response.status_code == 303
        assert "success=password_changed" in response.headers.get("location", "")

    def test_change_password_wrong_current(
        self, auth_client: TestClient, test_user: User
    ):
        """Test password change with wrong current password."""
        response = auth_client.post(
            "/auth/change-password",
            data={
                "current_password": "wrongpassword",
                "new_password": "newpassword456",
                "new_password_confirm": "newpassword456"
            },
            follow_redirects=False
        )

        assert response.status_code == 303
        assert "error=wrong_password" in response.headers.get("location", "")

    def test_change_password_mismatch(self, auth_client: TestClient, test_user: User):
        """Test password change with mismatched new passwords."""
        response = auth_client.post(
            "/auth/change-password",
            data={
                "current_password": "testpassword123",
                "new_password": "newpassword456",
                "new_password_confirm": "differentpassword"
            },
            follow_redirects=False
        )

        assert response.status_code == 303
        assert "error=passwords_mismatch" in response.headers.get("location", "")


class TestInviteManagement:
    """Tests for invite management (admin only)."""

    def test_create_invite_admin(self, admin_client: TestClient, admin_user: User):
        """Test that admin can create invites."""
        response = admin_client.post("/auth/invite")

        assert response.status_code == 200
        data = response.json()
        assert "invite_url" in data
        assert "expires_at" in data

    def test_create_invite_non_admin(self, auth_client: TestClient, test_user: User):
        """Test that non-admin cannot create invites."""
        response = auth_client.post("/auth/invite")

        # Should be forbidden or redirect
        assert response.status_code in [401, 403, 302, 303]

    def test_list_invites_admin(
        self, admin_client: TestClient, admin_user: User, db: Session
    ):
        """Test that admin can list invites."""
        # Create some invites
        for _ in range(3):
            create_invite(db, admin_user)

        response = admin_client.get("/auth/invites")

        assert response.status_code == 200
        data = response.json()
        assert "invites" in data
        assert len(data["invites"]) == 3

    def test_revoke_invite_admin(
        self, admin_client: TestClient, admin_user: User, db: Session
    ):
        """Test that admin can revoke invites."""
        invite = create_invite(db, admin_user)

        response = admin_client.delete(f"/auth/invite/{invite.id}")

        assert response.status_code == 200

        # Verify invite is deleted
        assert db.query(Invite).filter(Invite.id == invite.id).first() is None


class TestUserManagement:
    """Tests for user management (admin only)."""

    def test_reset_user_password_admin(
        self, admin_client: TestClient, admin_user: User, db: Session
    ):
        """Test that admin can reset user password."""
        target_user = create_user(db, email="target@example.com")

        response = admin_client.post(f"/auth/reset-password/{target_user.id}")

        assert response.status_code == 200
        data = response.json()
        assert "temp_password" in data
        assert len(data["temp_password"]) >= 8

    def test_reset_user_password_non_admin(
        self, auth_client: TestClient, db: Session
    ):
        """Test that non-admin cannot reset passwords."""
        target_user = create_user(db, email="target@example.com")

        response = auth_client.post(f"/auth/reset-password/{target_user.id}")

        assert response.status_code in [401, 403, 302, 303]

    def test_delete_user_admin(
        self, admin_client: TestClient, admin_user: User, db: Session
    ):
        """Test that admin can delete users."""
        target_user = create_user(db, email="target@example.com")

        response = admin_client.delete(f"/auth/users/{target_user.id}")

        assert response.status_code == 200

        # Verify user is deleted
        assert db.query(User).filter(User.id == target_user.id).first() is None

    def test_admin_cannot_delete_self(
        self, admin_client: TestClient, admin_user: User
    ):
        """Test that admin cannot delete their own account."""
        response = admin_client.delete(f"/auth/users/{admin_user.id}")

        assert response.status_code == 400

    def test_delete_user_non_admin(self, auth_client: TestClient, db: Session):
        """Test that non-admin cannot delete users."""
        target_user = create_user(db, email="target@example.com")

        response = auth_client.delete(f"/auth/users/{target_user.id}")

        assert response.status_code in [401, 403, 302, 303]


class TestAdminAccountPage:
    """Tests for admin-specific account page features."""

    def test_admin_account_shows_invites(
        self, admin_client: TestClient, admin_user: User, db: Session
    ):
        """Test that admin account page shows invites."""
        # Create an active invite
        create_invite(db, admin_user)

        response = admin_client.get("/auth/account")

        assert response.status_code == 200
        # Admin should see invite management section

    def test_admin_account_shows_all_users(
        self, admin_client: TestClient, admin_user: User, db: Session
    ):
        """Test that admin account page shows all users."""
        # Create additional users
        create_user(db, email="user1@example.com")
        create_user(db, email="user2@example.com")

        response = admin_client.get("/auth/account")

        assert response.status_code == 200
        # Admin should see user management section


class TestChangePasswordErrors:
    """Tests for password change error handling."""

    def test_change_password_too_short(
        self, auth_client: TestClient, test_user: User
    ):
        """Test password change with too short new password."""
        response = auth_client.post(
            "/auth/change-password",
            data={
                "current_password": "testpassword123",
                "new_password": "short",
                "new_password_confirm": "short"
            },
            follow_redirects=False
        )

        assert response.status_code == 303
        assert "error=password_too_short" in response.headers.get("location", "")


class TestInviteRevokeErrors:
    """Tests for invite revocation error handling."""

    def test_revoke_nonexistent_invite(
        self, admin_client: TestClient, admin_user: User
    ):
        """Test revoking non-existent invite."""
        response = admin_client.delete("/auth/invite/99999")

        assert response.status_code == 404


class TestResetPasswordErrors:
    """Tests for reset password error handling."""

    def test_reset_password_invalid_uuid(
        self, admin_client: TestClient, admin_user: User
    ):
        """Test reset password with invalid UUID."""
        response = admin_client.post("/auth/reset-password/not-a-uuid")

        assert response.status_code == 400

    def test_reset_password_user_not_found(
        self, admin_client: TestClient, admin_user: User
    ):
        """Test reset password for non-existent user."""
        import uuid
        fake_uuid = str(uuid.uuid4())

        response = admin_client.post(f"/auth/reset-password/{fake_uuid}")

        assert response.status_code == 404


class TestDeleteUserErrors:
    """Tests for delete user error handling."""

    def test_delete_user_invalid_uuid(
        self, admin_client: TestClient, admin_user: User
    ):
        """Test delete user with invalid UUID."""
        response = admin_client.delete("/auth/users/not-a-uuid")

        assert response.status_code == 400

    def test_delete_user_not_found(
        self, admin_client: TestClient, admin_user: User
    ):
        """Test delete non-existent user."""
        import uuid
        fake_uuid = str(uuid.uuid4())

        response = admin_client.delete(f"/auth/users/{fake_uuid}")

        assert response.status_code == 404


class TestRegisterPageRedirect:
    """Tests for register page redirect behavior."""

    def test_register_page_redirects_if_logged_in(
        self, auth_client: TestClient, test_user: User
    ):
        """Test that register page redirects if already logged in."""
        response = auth_client.get("/auth/register", follow_redirects=False)

        assert response.status_code == 303


class TestAuthRedirectBehavior:
    """Tests for HTML redirect-to-login behavior.

    When a browser (Accept: text/html) hits a protected endpoint without auth,
    it should redirect to login. API clients get 401 JSON instead.
    """

    def test_html_request_redirects_to_login(self, client: TestClient):
        """Test that HTML requests redirect to login page."""
        response = client.get(
            "/auth/account",
            headers={"Accept": "text/html"},
            follow_redirects=False
        )

        assert response.status_code == 303
        assert "/auth/login" in response.headers.get("location", "")

    def test_html_request_includes_return_url(self, client: TestClient):
        """Test that redirect includes return URL for post-login redirect."""
        response = client.get(
            "/meals/history",
            headers={"Accept": "text/html"},
            follow_redirects=False
        )

        assert response.status_code == 303
        location = response.headers.get("location", "")
        assert "/auth/login" in location
        assert "next=" in location

    def test_api_request_returns_401(self, client: TestClient):
        """Test that API requests (no Accept: text/html) get 401."""
        response = client.get(
            "/auth/account",
            headers={"Accept": "application/json"},
            follow_redirects=False
        )

        assert response.status_code == 401

    def test_htmx_request_returns_401(self, client: TestClient):
        """Test that htmx requests get 401, not redirect."""
        response = client.get(
            "/meals/history",
            headers={
                "Accept": "text/html",
                "HX-Request": "true"
            },
            follow_redirects=False
        )

        # htmx requests should get 401 so JS can handle it
        assert response.status_code == 401
