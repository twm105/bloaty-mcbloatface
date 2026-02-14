"""
Tests for error handling across the application.

Tests graceful handling of:
- Invalid IDs and 404 responses
- Claude API timeouts and errors
- File upload validation
- Malformed requests
"""
import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import patch, MagicMock, AsyncMock
from io import BytesIO

from app.models import User
from app.services.ai_service import ServiceUnavailableError, RateLimitError
from tests.factories import create_user, create_meal, create_symptom


class TestInvalidIdHandling:
    """Tests for handling invalid/non-existent IDs."""

    def test_meal_not_found(self, auth_client: TestClient, test_user: User):
        """Test 404 for non-existent meal."""
        response = auth_client.get("/meals/99999/edit-ingredients")
        assert response.status_code == 404

    def test_meal_delete_not_found(self, auth_client: TestClient, test_user: User):
        """Test 404 for deleting non-existent meal."""
        response = auth_client.delete("/meals/99999")
        assert response.status_code == 404

    def test_symptom_not_found(self, auth_client: TestClient, test_user: User):
        """Test 404 for non-existent symptom."""
        response = auth_client.get("/symptoms/99999/edit")
        assert response.status_code == 404

    def test_symptom_delete_not_found(self, auth_client: TestClient, test_user: User):
        """Test 404 for deleting non-existent symptom."""
        response = auth_client.delete("/symptoms/99999")
        assert response.status_code == 404

    def test_diagnosis_result_not_found(self, auth_client: TestClient, test_user: User):
        """Test 404 for non-existent diagnosis result."""
        response = auth_client.delete("/diagnosis/results/99999")
        assert response.status_code == 404

    def test_invalid_id_format(self, auth_client: TestClient, test_user: User):
        """Test handling of non-numeric ID."""
        response = auth_client.get("/meals/invalid/edit-ingredients")
        assert response.status_code == 422  # Validation error

    def test_negative_id(self, auth_client: TestClient, test_user: User):
        """Test handling of negative ID."""
        response = auth_client.get("/meals/-1/edit-ingredients")
        assert response.status_code in [404, 422]


class TestClaudeAPIErrors:
    """Tests for handling Claude API errors."""

    def test_service_unavailable_on_analyze(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test graceful handling of Claude service unavailable."""
        # Create meal with image path so analysis can be attempted
        meal = create_meal(db, test_user)
        meal.image_path = "/path/to/test/image.jpg"
        db.commit()

        with patch("app.api.meals.claude_service") as mock_service:
            mock_service.validate_meal_image = AsyncMock(return_value=True)
            mock_service.analyze_meal_image = AsyncMock(
                side_effect=ServiceUnavailableError("Service down")
            )

            response = auth_client.post(
                f"/meals/{meal.id}/analyze-image",
                follow_redirects=False
            )

            # Should return error page, not crash (200 with error HTML)
            assert response.status_code == 200

    def test_rate_limit_on_elaborate(
        self, auth_client: TestClient, test_user: User
    ):
        """Test graceful handling of rate limiting."""
        with patch("app.api.symptoms.claude_service") as mock_service:
            mock_service.elaborate_symptom_tags = AsyncMock(
                side_effect=RateLimitError("Rate limited")
            )

            response = auth_client.post(
                "/symptoms/tags/elaborate",
                json={"tags": [{"name": "test", "severity": 5}]}
            )

            # Should return appropriate error
            assert response.status_code in [429, 500]

    def test_timeout_on_diagnosis(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test handling of diagnosis timeout."""
        # Create enough data to trigger analysis
        for i in range(5):
            create_meal(db, test_user, name=f"Meal {i}")
            create_symptom(db, test_user, tags=[{"name": "bloating", "severity": 5}])

        with patch("app.api.diagnosis.DiagnosisService") as MockService:
            mock_instance = MagicMock()
            mock_instance.check_data_sufficiency.return_value = (True, 5, 5)
            mock_instance.run_diagnosis = AsyncMock(
                side_effect=ServiceUnavailableError("Timeout")
            )
            MockService.return_value = mock_instance

            response = auth_client.post(
                "/diagnosis/analyze",
                json={"async_mode": False}
            )

            # Should handle error gracefully
            assert response.status_code in [200, 503]


class TestFileUploadErrors:
    """Tests for file upload error handling during meal creation."""

    def test_upload_invalid_file_type_on_create(
        self, auth_client: TestClient, test_user: User
    ):
        """Test rejection of invalid file types during meal creation."""
        # Try to upload a text file as meal image
        response = auth_client.post(
            "/meals/create",
            files={"image": ("test.txt", BytesIO(b"not an image"), "text/plain")},
            data={"user_notes": "Test meal"},
            follow_redirects=False
        )

        # Should reject invalid file type
        assert response.status_code in [400, 415, 422]

    def test_meal_create_without_image(
        self, auth_client: TestClient, test_user: User
    ):
        """Test meal creation without image succeeds."""
        response = auth_client.post(
            "/meals/create",
            data={"user_notes": "Test meal without image"},
            follow_redirects=False
        )

        # Should succeed and redirect to edit-ingredients
        assert response.status_code == 303
        assert "/meals/" in response.headers.get("location", "")
        assert "/edit-ingredients" in response.headers.get("location", "")


class TestMalformedRequests:
    """Tests for handling malformed request data."""

    def test_invalid_json_body(self, auth_client: TestClient, test_user: User):
        """Test handling of invalid JSON."""
        response = auth_client.post(
            "/symptoms/tags/elaborate",
            content="not valid json",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 422

    def test_missing_required_fields(self, auth_client: TestClient, test_user: User):
        """Test handling of missing required fields."""
        response = auth_client.post(
            "/symptoms/create",
            data={
                "description": "Test"
                # Missing symptom_type and severity
            },
            follow_redirects=False
        )

        assert response.status_code == 422

    def test_invalid_severity_value(self, auth_client: TestClient, test_user: User):
        """Test handling of out-of-range severity."""
        response = auth_client.post(
            "/symptoms/create",
            data={
                "description": "Test",
                "symptom_type": "digestive",
                "severity": 100  # Out of range
            },
            follow_redirects=False
        )

        assert response.status_code == 400

    def test_invalid_date_format(self, auth_client: TestClient, test_user: User):
        """Test handling of invalid date format."""
        response = auth_client.post(
            "/symptoms/detect-episode",
            json={
                "tags": [{"name": "test", "severity": 5}],
                "start_time": "not a date"
            }
        )

        assert response.status_code in [400, 422, 500]

    def test_empty_tags_array(self, auth_client: TestClient, test_user: User):
        """Test handling of empty tags array."""
        import json

        response = auth_client.post(
            "/symptoms/create-tagged",
            data={"tags_json": json.dumps([])},  # Empty tags
            follow_redirects=False
        )

        # May succeed or fail gracefully
        assert response.status_code in [303, 400, 422]


class TestAuthorizationErrors:
    """Tests for authorization error handling."""

    def test_access_other_user_meal(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test forbidden access to other user's meal."""
        other_user = create_user(db, email="other@example.com")
        meal = create_meal(db, other_user)

        response = auth_client.get(f"/meals/{meal.id}/edit-ingredients")

        assert response.status_code in [403, 404]

    def test_delete_other_user_symptom(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test forbidden deletion of other user's symptom."""
        other_user = create_user(db, email="other@example.com")
        symptom = create_symptom(db, other_user)

        response = auth_client.delete(f"/symptoms/{symptom.id}")

        assert response.status_code in [403, 404]

    def test_non_admin_create_invite(
        self, auth_client: TestClient, test_user: User
    ):
        """Test non-admin cannot create invites."""
        response = auth_client.post("/auth/invite")

        assert response.status_code in [401, 403, 302, 303]


class TestDatabaseErrors:
    """Tests for database error handling."""

    def test_concurrent_delete_handling(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test graceful handling when resource deleted mid-operation."""
        meal = create_meal(db, test_user)
        meal_id = meal.id

        # Delete the meal
        db.delete(meal)
        db.commit()

        # Try to access it
        response = auth_client.get(f"/meals/{meal_id}/edit-ingredients")

        assert response.status_code == 404
