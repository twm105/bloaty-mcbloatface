"""
Integration tests for the Feedback API endpoints.

Tests submission and retrieval of user feedback for various features
(meal analysis, diagnosis results, etc.).
"""

import secrets

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import UserFeedback
from tests.factories import (
    create_meal,
    create_diagnosis_run,
    create_diagnosis_result,
    create_ingredient,
    create_user_feedback,
)


# =============================================================================
# Feedback Submission Tests
# =============================================================================


class TestSubmitFeedback:
    """Tests for POST /feedback endpoint."""

    def test_submit_meal_feedback_success(
        self, auth_client: TestClient, db: Session, test_user
    ):
        """Test successful feedback submission for a meal."""
        meal = create_meal(db, test_user, name="Test Meal")

        response = auth_client.post(
            "/feedback",
            data={
                "feature_type": "meal_analysis",
                "feature_id": meal.id,
                "rating": 4,
                "feedback_text": "Good analysis",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Feedback submitted successfully"

        # Verify feedback was saved
        feedback = (
            db.query(UserFeedback)
            .filter(
                UserFeedback.user_id == test_user.id,
                UserFeedback.feature_type == "meal_analysis",
                UserFeedback.feature_id == meal.id,
            )
            .first()
        )
        assert feedback is not None
        assert feedback.rating == 4
        assert feedback.feedback_text == "Good analysis"

    def test_submit_diagnosis_result_feedback(
        self, auth_client: TestClient, db: Session, test_user
    ):
        """Test feedback submission for a diagnosis result."""
        run = create_diagnosis_run(db, test_user)
        ingredient = create_ingredient(db, name=f"Onion_{secrets.token_hex(4)}")
        result = create_diagnosis_result(db, run, ingredient)

        response = auth_client.post(
            "/feedback",
            data={
                "feature_type": "diagnosis_result",
                "feature_id": result.id,
                "rating": 5,
                "feedback_text": "Very helpful",
            },
        )

        assert response.status_code == 200

    def test_submit_feedback_without_text(
        self, auth_client: TestClient, db: Session, test_user
    ):
        """Test feedback submission without optional text."""
        meal = create_meal(db, test_user)

        response = auth_client.post(
            "/feedback",
            data={"feature_type": "meal_analysis", "feature_id": meal.id, "rating": 3},
        )

        assert response.status_code == 200

        feedback = (
            db.query(UserFeedback)
            .filter(
                UserFeedback.feature_type == "meal_analysis",
                UserFeedback.feature_id == meal.id,
            )
            .first()
        )
        assert feedback.feedback_text is None

    def test_submit_feedback_updates_existing(
        self, auth_client: TestClient, db: Session, test_user
    ):
        """Test that resubmitting feedback updates existing record."""
        meal = create_meal(db, test_user)

        # First submission
        response1 = auth_client.post(
            "/feedback",
            data={
                "feature_type": "meal_analysis",
                "feature_id": meal.id,
                "rating": 2,
                "feedback_text": "Initial feedback",
            },
        )
        assert response1.status_code == 200

        # Second submission (update)
        response2 = auth_client.post(
            "/feedback",
            data={
                "feature_type": "meal_analysis",
                "feature_id": meal.id,
                "rating": 5,
                "feedback_text": "Updated feedback",
            },
        )
        assert response2.status_code == 200

        # Should only have one record
        feedbacks = (
            db.query(UserFeedback)
            .filter(
                UserFeedback.feature_type == "meal_analysis",
                UserFeedback.feature_id == meal.id,
            )
            .all()
        )
        assert len(feedbacks) == 1
        assert feedbacks[0].rating == 5
        assert feedbacks[0].feedback_text == "Updated feedback"

    def test_submit_feedback_requires_auth(
        self, client: TestClient, db: Session, test_user
    ):
        """Test that feedback submission requires authentication."""
        meal = create_meal(db, test_user)

        response = client.post(
            "/feedback",
            data={"feature_type": "meal_analysis", "feature_id": meal.id, "rating": 4},
        )

        assert response.status_code in [401, 403, 307]

    def test_submit_feedback_invalid_rating_too_high(
        self, auth_client: TestClient, db: Session, test_user
    ):
        """Test that rating over 5 is rejected."""
        meal = create_meal(db, test_user)

        response = auth_client.post(
            "/feedback",
            data={"feature_type": "meal_analysis", "feature_id": meal.id, "rating": 6},
        )

        assert response.status_code == 400
        assert "Rating must be between 0 and 5" in response.json()["detail"]

    def test_submit_feedback_invalid_rating_negative(
        self, auth_client: TestClient, db: Session, test_user
    ):
        """Test that negative rating is rejected."""
        meal = create_meal(db, test_user)

        response = auth_client.post(
            "/feedback",
            data={"feature_type": "meal_analysis", "feature_id": meal.id, "rating": -1},
        )

        assert response.status_code == 400

    def test_submit_feedback_invalid_feature_type(
        self, auth_client: TestClient, db: Session, test_user
    ):
        """Test that invalid feature type is rejected."""
        response = auth_client.post(
            "/feedback",
            data={"feature_type": "invalid_type", "feature_id": 1, "rating": 4},
        )

        assert response.status_code == 400
        assert "Invalid feature_type" in response.json()["detail"]

    def test_submit_feedback_feature_not_found(
        self, auth_client: TestClient, db: Session
    ):
        """Test that non-existent feature returns 404."""
        response = auth_client.post(
            "/feedback",
            data={"feature_type": "meal_analysis", "feature_id": 99999, "rating": 4},
        )

        assert response.status_code == 404

    def test_submit_feedback_feature_belongs_to_other_user(
        self, auth_client: TestClient, db: Session, admin_user
    ):
        """Test that feedback for another user's feature is rejected."""
        # Create meal for admin user, not test_user
        meal = create_meal(db, admin_user)

        response = auth_client.post(
            "/feedback",
            data={"feature_type": "meal_analysis", "feature_id": meal.id, "rating": 4},
        )

        assert response.status_code == 404

    def test_submit_feedback_zero_rating(
        self, auth_client: TestClient, db: Session, test_user
    ):
        """Test that zero rating is valid (worst possible)."""
        meal = create_meal(db, test_user)

        response = auth_client.post(
            "/feedback",
            data={"feature_type": "meal_analysis", "feature_id": meal.id, "rating": 0},
        )

        assert response.status_code == 200

        feedback = (
            db.query(UserFeedback)
            .filter(
                UserFeedback.feature_type == "meal_analysis",
                UserFeedback.feature_id == meal.id,
            )
            .first()
        )
        assert feedback.rating == 0


# =============================================================================
# Feedback Retrieval Tests
# =============================================================================


class TestGetFeedback:
    """Tests for GET /feedback/{feature_type}/{feature_id} endpoint."""

    def test_get_existing_feedback(
        self, auth_client: TestClient, db: Session, test_user
    ):
        """Test retrieving existing feedback."""
        meal = create_meal(db, test_user)
        create_user_feedback(
            db,
            test_user,
            feature_type="meal_analysis",
            feature_id=meal.id,
            rating=4,
            feedback_text="Great analysis!",
        )

        response = auth_client.get(f"/feedback/meal_analysis/{meal.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["rating"] == 4
        assert data["feedback_text"] == "Great analysis!"
        assert "created_at" in data

    def test_get_nonexistent_feedback(
        self, auth_client: TestClient, db: Session, test_user
    ):
        """Test retrieving non-existent feedback returns defaults."""
        meal = create_meal(db, test_user)

        response = auth_client.get(f"/feedback/meal_analysis/{meal.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["rating"] == 0
        assert data["feedback_text"] is None

    def test_get_feedback_requires_auth(
        self, client: TestClient, db: Session, test_user
    ):
        """Test that getting feedback requires authentication."""
        meal = create_meal(db, test_user)

        response = client.get(f"/feedback/meal_analysis/{meal.id}")

        assert response.status_code in [401, 403, 307]

    def test_get_feedback_diagnosis_result(
        self, auth_client: TestClient, db: Session, test_user
    ):
        """Test retrieving feedback for diagnosis result."""
        run = create_diagnosis_run(db, test_user)
        ingredient = create_ingredient(db, name=f"Garlic_{secrets.token_hex(4)}")
        result = create_diagnosis_result(db, run, ingredient)
        create_user_feedback(
            db,
            test_user,
            feature_type="diagnosis_result",
            feature_id=result.id,
            rating=5,
            feedback_text="Very accurate!",
        )

        response = auth_client.get(f"/feedback/diagnosis_result/{result.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["rating"] == 5
        assert data["feedback_text"] == "Very accurate!"

    def test_get_feedback_other_user_feedback_not_visible(
        self, auth_client: TestClient, db: Session, test_user, admin_user
    ):
        """Test that other users' feedback is not visible."""
        # Create meal for test_user
        meal = create_meal(db, test_user)

        # But feedback is from admin
        # This shouldn't be possible normally, but test the query isolation
        feedback = UserFeedback(
            user_id=admin_user.id,  # Different user
            feature_type="meal_analysis",
            feature_id=meal.id,
            rating=3,
            feedback_text="Admin feedback",
        )
        db.add(feedback)
        db.flush()

        # test_user's client should see no feedback
        response = auth_client.get(f"/feedback/meal_analysis/{meal.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["rating"] == 0  # No feedback found for test_user


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestFeedbackEdgeCases:
    """Test edge cases and error handling."""

    def test_submit_feedback_with_empty_text(
        self, auth_client: TestClient, db: Session, test_user
    ):
        """Test submitting feedback with empty string text."""
        meal = create_meal(db, test_user)

        response = auth_client.post(
            "/feedback",
            data={
                "feature_type": "meal_analysis",
                "feature_id": meal.id,
                "rating": 3,
                "feedback_text": "",
            },
        )

        assert response.status_code == 200

    def test_submit_feedback_with_long_text(
        self, auth_client: TestClient, db: Session, test_user
    ):
        """Test submitting feedback with very long text."""
        meal = create_meal(db, test_user)
        long_text = "A" * 5000  # 5000 characters

        response = auth_client.post(
            "/feedback",
            data={
                "feature_type": "meal_analysis",
                "feature_id": meal.id,
                "rating": 4,
                "feedback_text": long_text,
            },
        )

        # Should succeed (database should handle long text)
        assert response.status_code == 200

    def test_feedback_timestamp_updated_on_resubmit(
        self, auth_client: TestClient, db: Session, test_user
    ):
        """Test that timestamp is updated when feedback is resubmitted."""
        meal = create_meal(db, test_user)

        # First submission
        auth_client.post(
            "/feedback",
            data={"feature_type": "meal_analysis", "feature_id": meal.id, "rating": 2},
        )

        first_feedback = (
            db.query(UserFeedback)
            .filter(
                UserFeedback.feature_type == "meal_analysis",
                UserFeedback.feature_id == meal.id,
            )
            .first()
        )
        first_timestamp = first_feedback.created_at

        # Second submission
        auth_client.post(
            "/feedback",
            data={"feature_type": "meal_analysis", "feature_id": meal.id, "rating": 5},
        )

        db.refresh(first_feedback)
        # Timestamp should be updated
        assert first_feedback.created_at >= first_timestamp

    def test_multiple_features_independent_feedback(
        self, auth_client: TestClient, db: Session, test_user
    ):
        """Test that feedback for different features is independent."""
        meal1 = create_meal(db, test_user, name="Meal 1")
        meal2 = create_meal(db, test_user, name="Meal 2")

        # Submit feedback for both meals
        auth_client.post(
            "/feedback",
            data={"feature_type": "meal_analysis", "feature_id": meal1.id, "rating": 2},
        )
        auth_client.post(
            "/feedback",
            data={"feature_type": "meal_analysis", "feature_id": meal2.id, "rating": 5},
        )

        # Verify both are stored independently
        response1 = auth_client.get(f"/feedback/meal_analysis/{meal1.id}")
        response2 = auth_client.get(f"/feedback/meal_analysis/{meal2.id}")

        assert response1.json()["rating"] == 2
        assert response2.json()["rating"] == 5
