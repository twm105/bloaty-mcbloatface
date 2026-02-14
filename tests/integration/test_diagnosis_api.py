"""
Integration tests for Diagnosis API.

Tests the full diagnosis flow including:
- Authentication requirements
- Correlation analysis
- Feedback submission
- Result management
"""

from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import patch, MagicMock

from app.models import User, DiagnosisRun, DiagnosisResult
from tests.factories import (
    create_user,
    create_meal,
    create_symptom,
    create_ingredient,
    create_meal_ingredient,
    create_diagnosis_run,
    create_diagnosis_result,
)


class TestDiagnosisAuthentication:
    """Tests for diagnosis endpoint authentication."""

    def test_diagnosis_page_requires_auth(self, client: TestClient):
        """Test that diagnosis page requires authentication."""
        response = client.get("/diagnosis", follow_redirects=False)

        assert response.status_code in [302, 303, 307, 401]

    def test_methodology_page_requires_auth(self, client: TestClient):
        """Test that methodology page requires authentication."""
        response = client.get("/diagnosis/methodology", follow_redirects=False)

        assert response.status_code in [302, 303, 307, 401]

    def test_analyze_endpoint_requires_auth(self, client: TestClient):
        """Test that analyze endpoint requires authentication."""
        response = client.post("/diagnosis/analyze", json={}, follow_redirects=False)

        assert response.status_code in [302, 303, 307, 401]


class TestDiagnosisPage:
    """Tests for main diagnosis results page."""

    def test_diagnosis_page_renders_insufficient_data(
        self, auth_client: TestClient, test_user: User
    ):
        """Test diagnosis page shows insufficient data message."""
        response = auth_client.get("/diagnosis")

        assert response.status_code == 200
        # Should show insufficient data page
        assert (
            "insufficient" in response.text.lower() or "need" in response.text.lower()
        )

    def test_diagnosis_page_shows_results(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test diagnosis page shows results when available."""
        # Create a diagnosis run with results
        run = create_diagnosis_run(
            db, test_user, status="completed", sufficient_data=True
        )
        ingredient = create_ingredient(db, name="Onion")
        create_diagnosis_result(db, run, ingredient, confidence_score=0.85)

        response = auth_client.get("/diagnosis")

        assert response.status_code == 200
        # Should show results page with ingredient

    def test_methodology_page_renders(self, auth_client: TestClient, test_user: User):
        """Test methodology page renders."""
        response = auth_client.get("/diagnosis/methodology")

        assert response.status_code == 200


class TestDiagnosisAnalysis:
    """Tests for diagnosis analysis endpoint."""

    def test_analyze_insufficient_data(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test analysis returns insufficient data when not enough meals/symptoms."""
        response = auth_client.post("/diagnosis/analyze", json={"async_mode": False})

        assert response.status_code == 200
        data = response.json()
        assert data["sufficient_data"] is False
        assert "Insufficient data" in data.get("message", "")

    def test_analyze_no_correlations(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test analysis with data but no correlations."""
        # Create meals without symptoms or symptoms without meals
        for i in range(5):
            create_meal(db, test_user, name=f"Meal {i}")

        for i in range(3):
            create_symptom(db, test_user, tags=[{"name": "test", "severity": 5}])

        response = auth_client.post("/diagnosis/analyze", json={"async_mode": False})

        assert response.status_code == 200
        response.json()
        # Should return with message about no correlations or insufficient data

    def test_analyze_with_correlations(
        self, auth_client: TestClient, test_user: User, db: Session, mock_claude_service
    ):
        """Test analysis with correlated data."""
        # Create correlated meals and symptoms
        ingredient = create_ingredient(db, name="Trigger Food")

        for i in range(5):
            meal = create_meal(db, test_user, name=f"Meal {i}")
            create_meal_ingredient(db, meal, ingredient)

            # Create symptom shortly after meal
            create_symptom(
                db,
                test_user,
                tags=[{"name": "bloating", "severity": 7}],
                timestamp=meal.timestamp + timedelta(hours=1),
            )

        with patch("app.api.diagnosis.DiagnosisService") as MockService:
            mock_instance = MagicMock()
            mock_instance.check_data_sufficiency.return_value = (True, 5, 5)
            mock_instance.get_correlated_ingredient_ids.return_value = [ingredient.id]
            mock_instance.get_holistic_ingredient_data.return_value = {
                "ingredient_id": ingredient.id,
                "ingredient_name": "Trigger Food",
                "confidence_score": 0.8,
                "confidence_level": "high",
            }
            mock_instance.MIN_MEALS = 3
            mock_instance.MIN_SYMPTOM_OCCURRENCES = 2
            MockService.return_value = mock_instance

            response = auth_client.post("/diagnosis/analyze", json={"async_mode": True})

            assert response.status_code == 200
            data = response.json()
            assert data["status"] in ["processing", "completed"]

    def test_analyze_custom_thresholds(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test analysis with custom minimum thresholds."""
        response = auth_client.post(
            "/diagnosis/analyze",
            json={"min_meals": 1, "min_symptom_occurrences": 1, "async_mode": False},
        )

        assert response.status_code == 200


class TestDiagnosisFeedback:
    """Tests for feedback submission."""

    def test_submit_feedback_success(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test submitting feedback on a result."""
        run = create_diagnosis_run(db, test_user, status="completed")
        ingredient = create_ingredient(db, name="Test Ingredient")
        result = create_diagnosis_result(db, run, ingredient)

        response = auth_client.post(
            "/diagnosis/feedback",
            json={
                "result_id": result.id,
                "rating": 4,
                "feedback_text": "This seems accurate",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "success" in data["message"].lower()

    def test_submit_feedback_invalid_rating(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test feedback with invalid rating."""
        run = create_diagnosis_run(db, test_user)
        ingredient = create_ingredient(db, name="Test")
        result = create_diagnosis_result(db, run, ingredient)

        response = auth_client.post(
            "/diagnosis/feedback",
            json={
                "result_id": result.id,
                "rating": 10,  # Invalid: > 5
                "feedback_text": "Test",
            },
        )

        assert response.status_code == 400

    def test_submit_feedback_nonexistent_result(
        self, auth_client: TestClient, test_user: User
    ):
        """Test feedback for non-existent result."""
        response = auth_client.post(
            "/diagnosis/feedback", json={"result_id": 99999, "rating": 3}
        )

        assert response.status_code == 404

    def test_submit_feedback_other_user_result(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test cannot submit feedback for another user's result."""
        other_user = create_user(db, email="other@example.com")
        run = create_diagnosis_run(db, other_user)
        ingredient = create_ingredient(db, name="Test")
        result = create_diagnosis_result(db, run, ingredient)

        response = auth_client.post(
            "/diagnosis/feedback", json={"result_id": result.id, "rating": 3}
        )

        assert response.status_code == 404

    def test_update_existing_feedback(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test updating existing feedback."""
        run = create_diagnosis_run(db, test_user)
        ingredient = create_ingredient(db, name="Test")
        result = create_diagnosis_result(db, run, ingredient)

        # Submit initial feedback
        auth_client.post(
            "/diagnosis/feedback", json={"result_id": result.id, "rating": 3}
        )

        # Update feedback
        response = auth_client.post(
            "/diagnosis/feedback",
            json={
                "result_id": result.id,
                "rating": 5,
                "feedback_text": "Updated opinion",
            },
        )

        assert response.status_code == 200


class TestDiagnosisReset:
    """Tests for resetting diagnosis data."""

    def test_reset_diagnosis_data(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test resetting all diagnosis data."""
        # Create diagnosis data
        run = create_diagnosis_run(db, test_user)
        ingredient = create_ingredient(db, name="Test")
        create_diagnosis_result(db, run, ingredient)

        response = auth_client.post("/diagnosis/reset")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify data is deleted
        remaining = (
            db.query(DiagnosisRun).filter(DiagnosisRun.user_id == test_user.id).count()
        )
        assert remaining == 0

    def test_reset_empty_data(self, auth_client: TestClient, test_user: User):
        """Test reset when no diagnosis data exists."""
        response = auth_client.post("/diagnosis/reset")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["runs_deleted"] == 0


class TestDiagnosisResultDeletion:
    """Tests for deleting individual results."""

    def test_delete_result(self, auth_client: TestClient, test_user: User, db: Session):
        """Test deleting a diagnosis result."""
        run = create_diagnosis_run(db, test_user)
        ingredient = create_ingredient(db, name="Test")
        result = create_diagnosis_result(db, run, ingredient)
        result_id = result.id

        response = auth_client.delete(f"/diagnosis/results/{result_id}")

        assert response.status_code == 200

        # Verify result is deleted
        remaining = (
            db.query(DiagnosisResult).filter(DiagnosisResult.id == result_id).first()
        )
        assert remaining is None

    def test_delete_nonexistent_result(self, auth_client: TestClient, test_user: User):
        """Test deleting non-existent result."""
        response = auth_client.delete("/diagnosis/results/99999")

        assert response.status_code == 404

    def test_cannot_delete_other_user_result(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test cannot delete another user's result."""
        other_user = create_user(db, email="other@example.com")
        run = create_diagnosis_run(db, other_user)
        ingredient = create_ingredient(db, name="Test")
        result = create_diagnosis_result(db, run, ingredient)

        response = auth_client.delete(f"/diagnosis/results/{result.id}")

        assert response.status_code == 404

        # Verify result still exists
        remaining = (
            db.query(DiagnosisResult).filter(DiagnosisResult.id == result.id).first()
        )
        assert remaining is not None
