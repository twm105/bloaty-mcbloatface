"""Integration tests for admin dashboard routes."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import (
    create_meal,
    create_symptom,
    create_user,
    create_ai_usage_log,
)


class TestDashboardAccess:
    def test_unauthenticated_redirects(self, client: TestClient):
        response = client.get("/admin/dashboard", follow_redirects=False)
        # Should get 401 (handled by auth exception handler)
        assert response.status_code in (401, 307, 303)

    def test_non_admin_rejected(self, auth_client: TestClient):
        response = auth_client.get("/admin/dashboard")
        assert response.status_code == 403

    def test_admin_can_access(self, admin_client: TestClient):
        response = admin_client.get("/admin/dashboard")
        assert response.status_code == 200
        assert "Usage Dashboard" in response.text

    def test_admin_sees_user_table(self, admin_client: TestClient, db: Session):
        user = create_user(db, email="visible@example.com")
        create_meal(db, user)

        response = admin_client.get("/admin/dashboard")
        assert response.status_code == 200
        assert "visible@example.com" in response.text


class TestUserDetailAccess:
    def test_non_admin_rejected(self, auth_client: TestClient, test_user):
        response = auth_client.get(f"/admin/dashboard/user/{test_user.id}")
        assert response.status_code == 403

    def test_admin_can_access(self, admin_client: TestClient, db: Session):
        user = create_user(db, email="detailview@example.com")
        response = admin_client.get(f"/admin/dashboard/user/{user.id}")
        assert response.status_code == 200
        assert "detailview@example.com" in response.text

    def test_nonexistent_user_404(self, admin_client: TestClient):
        fake_id = uuid.uuid4()
        response = admin_client.get(f"/admin/dashboard/user/{fake_id}")
        assert response.status_code == 404

    def test_invalid_uuid_400(self, admin_client: TestClient):
        response = admin_client.get("/admin/dashboard/user/not-a-uuid")
        assert response.status_code == 400

    def test_detail_shows_metrics(self, admin_client: TestClient, db: Session):
        user = create_user(db, email="metrics@example.com")
        create_meal(db, user, status="published")
        create_symptom(db, user)
        create_ai_usage_log(db, user, estimated_cost_cents=250.0)

        response = admin_client.get(f"/admin/dashboard/user/{user.id}")
        assert response.status_code == 200
        content = response.text
        assert "Meals" in content
        assert "Symptoms" in content
        assert "API Spend" in content
        assert "$2.50" in content
