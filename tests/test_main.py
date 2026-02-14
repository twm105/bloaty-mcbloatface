import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app
from app.models.user import User
from app.models.user_settings import UserSettings
from tests.factories import create_user

client = TestClient(app)


def test_root_requires_auth():
    """Test that root endpoint redirects to login when not authenticated."""
    response = client.get("/", follow_redirects=False)
    # Should redirect to login or return 401
    assert response.status_code in [303, 401]


def test_health_check():
    """Test that health check endpoint is accessible without auth."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


class TestMainRoutes:
    """Tests for main application routes when authenticated."""

    def test_home_page_renders(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test home page renders for logged in user."""
        response = auth_client.get("/")
        assert response.status_code == 200
        # Should contain the main navigation
        assert "meal" in response.text.lower() or "symptom" in response.text.lower()

    def test_home_page_with_disclaimer_acknowledged(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test home page with disclaimer already acknowledged."""
        # Create user settings with disclaimer acknowledged
        settings = UserSettings(
            user_id=test_user.id,
            disclaimer_acknowledged=True
        )
        db.add(settings)
        db.commit()

        response = auth_client.get("/")
        assert response.status_code == 200

    def test_home_page_without_settings(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test home page when user has no settings record."""
        # Ensure no settings exist
        db.query(UserSettings).filter(UserSettings.user_id == test_user.id).delete()
        db.commit()

        response = auth_client.get("/")
        assert response.status_code == 200

    def test_analysis_page_renders(
        self, auth_client: TestClient, test_user: User
    ):
        """Test analysis page renders."""
        response = auth_client.get("/analysis")
        assert response.status_code == 200

    def test_settings_page_renders(
        self, auth_client: TestClient, test_user: User
    ):
        """Test settings page renders."""
        response = auth_client.get("/settings")
        assert response.status_code == 200

    def test_analysis_requires_auth(self, client: TestClient):
        """Test analysis page requires authentication."""
        response = client.get("/analysis", follow_redirects=False)
        assert response.status_code in [303, 401]

    def test_settings_requires_auth(self, client: TestClient):
        """Test settings page requires authentication."""
        response = client.get("/settings", follow_redirects=False)
        assert response.status_code in [303, 401]
