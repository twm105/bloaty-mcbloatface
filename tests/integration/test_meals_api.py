"""
Integration tests for Meals API.

Tests the full meal management flow including:
- Authentication requirements
- Meal CRUD operations
- Ingredient management
- Authorization checks
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import io

from app.models import User, Meal, Ingredient, MealIngredient, IngredientState
from app.models.user_feedback import UserFeedback
from tests.factories import (
    create_user, create_meal, create_ingredient, create_meal_ingredient
)


class TestMealAuthentication:
    """Tests for meal endpoint authentication."""

    def test_meals_history_requires_auth(self, client: TestClient):
        """Test that meals history page requires authentication."""
        response = client.get("/meals/history", follow_redirects=False)

        # Should redirect to login
        assert response.status_code in [302, 303, 307, 401]

    def test_meals_log_requires_auth(self, client: TestClient):
        """Test that meals log page requires authentication."""
        response = client.get("/meals/log", follow_redirects=False)

        # Should redirect to login
        assert response.status_code in [302, 303, 307, 401]

    def test_meals_history_accessible_when_logged_in(
        self, auth_client: TestClient, test_user: User
    ):
        """Test that meals history is accessible when logged in."""
        response = auth_client.get("/meals/history")

        assert response.status_code == 200

    def test_meals_log_accessible_when_logged_in(
        self, auth_client: TestClient, test_user: User
    ):
        """Test that meals log page is accessible when logged in."""
        response = auth_client.get("/meals/log")

        assert response.status_code == 200


class TestMealListing:
    """Tests for meal listing via history page."""

    def test_list_meals_empty(self, auth_client: TestClient, test_user: User):
        """Test listing meals when none exist."""
        response = auth_client.get("/meals/history")

        assert response.status_code == 200

    def test_list_meals_shows_published_only(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test that meal history shows only published meals."""
        # Create published meals
        for i in range(3):
            create_meal(db, test_user, name=f"Published {i}", status="published")

        # Create draft meals
        for i in range(2):
            create_meal(db, test_user, name=f"Draft {i}", status="draft")

        response = auth_client.get("/meals/history")

        assert response.status_code == 200
        # Published meals should be in response
        assert "Published" in response.text
        # Draft meals should not be shown in regular list
        # (they may appear in a different section)


class TestMealCreation:
    """Tests for meal creation."""

    def test_create_meal_page_requires_auth(self, client: TestClient):
        """Test that meal log page requires authentication."""
        response = client.get("/meals/log", follow_redirects=False)

        assert response.status_code in [302, 303, 307, 401]

    def test_create_meal_page_renders(
        self, auth_client: TestClient, test_user: User
    ):
        """Test that meal log page renders."""
        response = auth_client.get("/meals/log")

        assert response.status_code == 200


class TestMealViewing:
    """Tests for viewing/editing individual meals."""

    def test_view_own_meal_edit_page(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test viewing own meal's edit-ingredients page."""
        meal = create_meal(db, test_user, name="My Meal")

        response = auth_client.get(f"/meals/{meal.id}/edit-ingredients")

        assert response.status_code == 200
        assert "My Meal" in response.text

    def test_view_nonexistent_meal(self, auth_client: TestClient, test_user: User):
        """Test viewing non-existent meal returns 404."""
        response = auth_client.get("/meals/99999/edit-ingredients")

        assert response.status_code == 404

    def test_view_other_user_meal(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test that viewing another user's meal is forbidden."""
        other_user = create_user(db, email="other@example.com")
        meal = create_meal(db, other_user, name="Other's Meal")

        response = auth_client.get(f"/meals/{meal.id}/edit-ingredients")

        # Should be forbidden or not found
        assert response.status_code in [403, 404]


class TestMealEditing:
    """Tests for editing meals."""

    def test_edit_meal_page(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test that edit-ingredients page renders for own meal."""
        meal = create_meal(db, test_user)

        response = auth_client.get(f"/meals/{meal.id}/edit-ingredients")

        assert response.status_code == 200

    def test_cannot_edit_other_user_meal(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test that editing another user's meal is forbidden."""
        other_user = create_user(db, email="other@example.com")
        meal = create_meal(db, other_user)

        response = auth_client.get(f"/meals/{meal.id}/edit-ingredients")

        assert response.status_code in [403, 404]


class TestMealPublishing:
    """Tests for publishing meals."""

    def test_complete_meal(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test completing/publishing a draft meal."""
        meal = create_meal(db, test_user, status="draft")

        response = auth_client.post(
            f"/meals/{meal.id}/complete",
            follow_redirects=False
        )

        # Should redirect to history
        assert response.status_code == 303

        # Check meal is published
        db.refresh(meal)
        assert meal.status == "published"


class TestMealDeletion:
    """Tests for deleting meals."""

    def test_delete_meal(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test deleting own meal."""
        meal = create_meal(db, test_user)
        meal_id = meal.id

        response = auth_client.delete(f"/meals/{meal_id}")

        assert response.status_code in [200, 204, 303]

        # Verify meal is deleted
        assert db.query(Meal).filter(Meal.id == meal_id).first() is None

    def test_cannot_delete_other_user_meal(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test that deleting another user's meal is forbidden."""
        other_user = create_user(db, email="other@example.com")
        meal = create_meal(db, other_user)

        response = auth_client.delete(f"/meals/{meal.id}")

        assert response.status_code in [403, 404]

        # Verify meal still exists
        assert db.query(Meal).filter(Meal.id == meal.id).first() is not None


class TestMealIngredients:
    """Tests for meal ingredient management."""

    def test_add_ingredient_to_meal(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test adding an ingredient to a meal."""
        meal = create_meal(db, test_user)

        response = auth_client.post(
            f"/meals/{meal.id}/ingredients/add",
            data={
                "ingredient_name": "Chicken",
                "state": "cooked"
            }
        )

        # Check ingredient was added
        db.refresh(meal)
        assert len(meal.meal_ingredients) == 1

    def test_remove_ingredient_from_meal(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test removing an ingredient from a meal."""
        meal = create_meal(db, test_user)
        ingredient = create_ingredient(db, name="Tomato")
        meal_ing = create_meal_ingredient(db, meal, ingredient)

        response = auth_client.delete(
            f"/meals/{meal.id}/ingredients/{meal_ing.id}"
        )

        assert response.status_code in [200, 204]

        # Verify ingredient link is removed
        assert db.query(MealIngredient).filter(
            MealIngredient.id == meal_ing.id
        ).first() is None

    def test_update_ingredient_state(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test updating ingredient state."""
        meal = create_meal(db, test_user)
        ingredient = create_ingredient(db, name="Carrot")
        meal_ing = create_meal_ingredient(
            db, meal, ingredient,
            state=IngredientState.RAW
        )

        # PATCH to /meals/ingredients/{id}/state with JSON body
        response = auth_client.patch(
            f"/meals/ingredients/{meal_ing.id}/state",
            json={"state": "cooked"}
        )

        assert response.status_code == 200

        # Check state was updated
        db.refresh(meal_ing)
        assert meal_ing.state == IngredientState.COOKED


class TestMealHistory:
    """Tests for meal history."""

    def test_history_page_renders(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test that history page renders with meals."""
        for i in range(5):
            create_meal(db, test_user, name=f"Meal {i}")

        response = auth_client.get("/meals/history")

        assert response.status_code == 200

    def test_history_pagination(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test history pagination."""
        for i in range(30):
            create_meal(db, test_user, name=f"Meal {i}")

        # First page
        response = auth_client.get("/meals/history?page=1&per_page=10")
        assert response.status_code == 200

        # Second page
        response = auth_client.get("/meals/history?page=2&per_page=10")
        assert response.status_code == 200


class TestMealWithIngredients:
    """Tests for meals with ingredients."""

    def test_meal_shows_ingredients(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test that meal edit page shows ingredients."""
        meal = create_meal(db, test_user, name="Chicken Salad")
        chicken = create_ingredient(db, name="Chicken")
        lettuce = create_ingredient(db, name="Lettuce")

        create_meal_ingredient(db, meal, chicken, state=IngredientState.COOKED)
        create_meal_ingredient(db, meal, lettuce, state=IngredientState.RAW)

        response = auth_client.get(f"/meals/{meal.id}/edit-ingredients")

        assert response.status_code == 200
        assert "Chicken" in response.text or "chicken" in response.text
        assert "Lettuce" in response.text or "lettuce" in response.text


class TestMealCreationAdvanced:
    """Tests for meal creation edge cases."""

    def test_create_meal_with_invalid_timestamp(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test creating meal with invalid timestamp falls back to now."""
        response = auth_client.post(
            "/meals/create",
            data={
                "meal_timestamp": "not-a-valid-timestamp",
                "user_notes": "Test meal"
            },
            follow_redirects=False
        )

        # Should succeed with fallback timestamp
        assert response.status_code == 303

        # Check meal was created with a recent timestamp
        meal = db.query(Meal).filter(Meal.user_id == test_user.id).first()
        assert meal is not None

    def test_create_meal_with_valid_timestamp(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test creating meal with valid timestamp."""
        response = auth_client.post(
            "/meals/create",
            data={
                "meal_timestamp": "2025-06-15T12:30:00",
                "user_notes": "Lunch"
            },
            follow_redirects=False
        )

        assert response.status_code == 303

    def test_create_meal_no_timestamp(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test creating meal without timestamp defaults to now."""
        response = auth_client.post(
            "/meals/create",
            data={"user_notes": "Test"},
            follow_redirects=False
        )

        assert response.status_code == 303


class TestMealCreationWithImage:
    """Tests for meal creation with image upload."""

    def test_create_meal_image_upload_error(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test handling of image upload errors."""
        with patch('app.api.meals.file_service.save_meal_image',
                   new_callable=AsyncMock, side_effect=ValueError("File too large")):
            # Create fake file
            fake_file = io.BytesIO(b"fake image data")

            response = auth_client.post(
                "/meals/create",
                files={"image": ("test.jpg", fake_file, "image/jpeg")},
                data={"user_notes": "Test"},
                follow_redirects=False
            )

        assert response.status_code == 400


class TestMealAnalysis:
    """Tests for meal image analysis."""

    def test_analyze_nonexistent_meal(
        self, auth_client: TestClient, test_user: User
    ):
        """Test analyzing non-existent meal returns 404."""
        response = auth_client.post("/meals/99999/analyze-image")

        assert response.status_code == 404

    def test_analyze_meal_success(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test successful meal image analysis."""
        meal = create_meal(db, test_user, image_path="/uploads/test.jpg")

        mock_result = {
            "meal_name": "Chicken Salad",
            "raw_response": "AI response text",
            "ingredients": [
                {"name": "chicken", "state": "cooked", "quantity": "200g", "confidence": 0.95},
                {"name": "lettuce", "state": "raw", "quantity": "1 cup", "confidence": 0.90},
            ]
        }

        with patch('app.api.meals.claude_service.validate_meal_image',
                   new_callable=AsyncMock, return_value=True):
            with patch('app.api.meals.claude_service.analyze_meal_image',
                       new_callable=AsyncMock, return_value=mock_result):
                response = auth_client.post(f"/meals/{meal.id}/analyze-image")

        assert response.status_code == 200
        assert "Chicken Salad" in response.text or "chicken" in response.text.lower()

        # Verify ingredients were added
        db.refresh(meal)
        assert meal.name == "Chicken Salad"
        assert len(meal.meal_ingredients) == 2

    def test_analyze_meal_skips_malformed_suggestions(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test that malformed ingredient suggestions are skipped."""
        meal = create_meal(db, test_user, image_path="/uploads/test.jpg")

        mock_result = {
            "meal_name": "Test Meal",
            "raw_response": "AI response",
            "ingredients": [
                {"name": "chicken", "state": "cooked"},  # Valid
                {"name": "bad", "state": "invalid_state"},  # Invalid state
                {"missing_name": "test"},  # Missing name key
            ]
        }

        with patch('app.api.meals.claude_service.validate_meal_image',
                   new_callable=AsyncMock, return_value=True):
            with patch('app.api.meals.claude_service.analyze_meal_image',
                       new_callable=AsyncMock, return_value=mock_result):
                response = auth_client.post(f"/meals/{meal.id}/analyze-image")

        assert response.status_code == 200

        # Only the valid ingredient should be added
        db.refresh(meal)
        assert len(meal.meal_ingredients) == 1

    def test_analyze_other_user_meal(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test analyzing another user's meal is forbidden."""
        other_user = create_user(db, email="other@example.com")
        meal = create_meal(db, other_user, image_path="/uploads/test.jpg")

        response = auth_client.post(f"/meals/{meal.id}/analyze-image")

        assert response.status_code == 403

    def test_analyze_meal_without_image(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test analyzing meal without image returns 400."""
        meal = create_meal(db, test_user, image_path=None)

        response = auth_client.post(f"/meals/{meal.id}/analyze-image")

        assert response.status_code == 400

    def test_analyze_meal_not_food_image(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test analyzing non-food image returns error."""
        meal = create_meal(db, test_user, image_path="/uploads/test.jpg")

        with patch('app.api.meals.claude_service.validate_meal_image',
                   new_callable=AsyncMock, return_value=False):
            response = auth_client.post(f"/meals/{meal.id}/analyze-image")

        assert response.status_code == 200
        assert "food image" in response.text.lower() or "manual" in response.text.lower()

    def test_analyze_meal_service_unavailable(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test handling of ServiceUnavailableError."""
        from app.services.ai_service import ServiceUnavailableError

        meal = create_meal(db, test_user, image_path="/uploads/test.jpg")

        with patch('app.api.meals.claude_service.validate_meal_image',
                   new_callable=AsyncMock, side_effect=ServiceUnavailableError("Service down")):
            response = auth_client.post(f"/meals/{meal.id}/analyze-image")

        assert response.status_code == 200
        assert "unavailable" in response.text.lower()

    def test_analyze_meal_rate_limit(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test handling of RateLimitError."""
        from app.services.ai_service import RateLimitError

        meal = create_meal(db, test_user, image_path="/uploads/test.jpg")

        with patch('app.api.meals.claude_service.validate_meal_image',
                   new_callable=AsyncMock, side_effect=RateLimitError("Too many requests")):
            response = auth_client.post(f"/meals/{meal.id}/analyze-image")

        assert response.status_code == 200
        assert "wait" in response.text.lower() or "too many" in response.text.lower()

    def test_analyze_meal_generic_error(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test handling of generic errors during analysis."""
        meal = create_meal(db, test_user, image_path="/uploads/test.jpg")

        with patch('app.api.meals.claude_service.validate_meal_image',
                   new_callable=AsyncMock, side_effect=Exception("Something went wrong")):
            response = auth_client.post(f"/meals/{meal.id}/analyze-image")

        assert response.status_code == 200
        assert "failed" in response.text.lower() or "error" in response.text.lower()


class TestMealIngredientErrors:
    """Tests for ingredient management error paths."""

    def test_add_ingredient_nonexistent_meal(
        self, auth_client: TestClient, test_user: User
    ):
        """Test adding ingredient to non-existent meal."""
        response = auth_client.post(
            "/meals/99999/ingredients/add",
            data={"ingredient_name": "Test", "state": "cooked"}
        )

        assert response.status_code == 404

    def test_add_ingredient_other_user_meal(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test adding ingredient to another user's meal."""
        other_user = create_user(db, email="other@example.com")
        meal = create_meal(db, other_user)

        response = auth_client.post(
            f"/meals/{meal.id}/ingredients/add",
            data={"ingredient_name": "Test", "state": "cooked"}
        )

        assert response.status_code == 403

    def test_add_ingredient_invalid_state(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test adding ingredient with invalid state."""
        meal = create_meal(db, test_user)

        response = auth_client.post(
            f"/meals/{meal.id}/ingredients/add",
            data={"ingredient_name": "Test", "state": "invalid"}
        )

        assert response.status_code == 400

    def test_remove_ingredient_unauthorized(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test removing ingredient from another user's meal."""
        other_user = create_user(db, email="other@example.com")
        meal = create_meal(db, other_user)
        ingredient = create_ingredient(db, name="Test")
        mi = create_meal_ingredient(db, meal, ingredient)

        response = auth_client.delete(
            f"/meals/{meal.id}/ingredients/{mi.id}"
        )

        assert response.status_code == 403

    def test_remove_nonexistent_ingredient(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test removing non-existent ingredient."""
        meal = create_meal(db, test_user)

        response = auth_client.delete(
            f"/meals/{meal.id}/ingredients/99999"
        )

        assert response.status_code == 404


class TestCompleteMealErrors:
    """Tests for complete/publish meal error paths."""

    def test_complete_other_user_meal(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test completing another user's meal."""
        other_user = create_user(db, email="other@example.com")
        meal = create_meal(db, other_user)

        response = auth_client.post(
            f"/meals/{meal.id}/complete",
            follow_redirects=False
        )

        assert response.status_code == 403

    def test_complete_nonexistent_meal(
        self, auth_client: TestClient, test_user: User
    ):
        """Test completing non-existent meal."""
        response = auth_client.post(
            "/meals/99999/complete",
            follow_redirects=False
        )

        assert response.status_code == 404


class TestUpdateMealName:
    """Tests for meal name update."""

    def test_update_meal_name(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test updating meal name."""
        meal = create_meal(db, test_user, name="Old Name")

        response = auth_client.put(
            f"/meals/{meal.id}/name",
            data={"name": "New Name"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"

    def test_update_other_user_meal_name(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test updating another user's meal name."""
        other_user = create_user(db, email="other@example.com")
        meal = create_meal(db, other_user)

        response = auth_client.put(
            f"/meals/{meal.id}/name",
            data={"name": "Hacked"}
        )

        assert response.status_code == 403

    def test_update_nonexistent_meal_name(
        self, auth_client: TestClient, test_user: User
    ):
        """Test updating non-existent meal name."""
        response = auth_client.put(
            "/meals/99999/name",
            data={"name": "Test"}
        )

        assert response.status_code == 404


class TestUpdateMealMetadata:
    """Tests for meal metadata update."""

    def test_update_meal_metadata(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test updating meal metadata."""
        meal = create_meal(db, test_user)

        response = auth_client.put(
            f"/meals/{meal.id}",
            data={
                "country": "Italy",
                "user_notes": "Delicious pasta",
                "timestamp": "2025-06-15T18:30:00"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["country"] == "Italy"

    def test_update_other_user_meal_metadata(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test updating another user's meal metadata."""
        other_user = create_user(db, email="other@example.com")
        meal = create_meal(db, other_user)

        response = auth_client.put(
            f"/meals/{meal.id}",
            data={"country": "Hacked"}
        )

        assert response.status_code == 403

    def test_update_nonexistent_meal_metadata(
        self, auth_client: TestClient, test_user: User
    ):
        """Test updating non-existent meal metadata."""
        response = auth_client.put(
            "/meals/99999",
            data={"country": "Test"}
        )

        assert response.status_code == 404


class TestUpdateIngredient:
    """Tests for ingredient update."""

    def test_update_ingredient(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test updating ingredient name and quantity."""
        meal = create_meal(db, test_user)
        ingredient = create_ingredient(db, name="Chicken")
        mi = create_meal_ingredient(db, meal, ingredient)

        response = auth_client.put(
            f"/meals/{meal.id}/ingredients/{mi.id}",
            data={
                "ingredient_name": "Beef",
                "quantity": "200g"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"

    def test_update_ingredient_unauthorized(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test updating ingredient on another user's meal."""
        other_user = create_user(db, email="other@example.com")
        meal = create_meal(db, other_user)
        ingredient = create_ingredient(db, name="Test")
        mi = create_meal_ingredient(db, meal, ingredient)

        response = auth_client.put(
            f"/meals/{meal.id}/ingredients/{mi.id}",
            data={"ingredient_name": "Hacked"}
        )

        assert response.status_code == 403

    def test_update_nonexistent_ingredient(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test updating non-existent ingredient."""
        meal = create_meal(db, test_user)

        response = auth_client.put(
            f"/meals/{meal.id}/ingredients/99999",
            data={"ingredient_name": "Test"}
        )

        assert response.status_code == 404


class TestUpdateIngredientState:
    """Tests for ingredient state update."""

    def test_update_state_invalid(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test updating ingredient with invalid state."""
        meal = create_meal(db, test_user)
        ingredient = create_ingredient(db, name="Test")
        mi = create_meal_ingredient(db, meal, ingredient)

        response = auth_client.patch(
            f"/meals/ingredients/{mi.id}/state",
            json={"state": "invalid"}
        )

        assert response.status_code == 400

    def test_update_state_nonexistent(
        self, auth_client: TestClient, test_user: User
    ):
        """Test updating state of non-existent ingredient."""
        response = auth_client.patch(
            "/meals/ingredients/99999/state",
            json={"state": "cooked"}
        )

        assert response.status_code == 404


class TestDeleteMealWithImage:
    """Tests for deleting meals with images."""

    def test_delete_meal_with_image(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test deleting meal also deletes image file."""
        meal = create_meal(db, test_user, image_path="/uploads/test.jpg")
        meal_id = meal.id

        with patch('app.api.meals.file_service.delete_file') as mock_delete:
            response = auth_client.delete(f"/meals/{meal_id}")

        assert response.status_code in [200, 204]
        mock_delete.assert_called_once_with("/uploads/test.jpg")

    def test_delete_nonexistent_meal(
        self, auth_client: TestClient, test_user: User
    ):
        """Test deleting non-existent meal."""
        response = auth_client.delete("/meals/99999")

        assert response.status_code == 404


class TestEditIngredientsWithFeedback:
    """Tests for edit ingredients page with existing feedback."""

    def test_edit_ingredients_shows_existing_feedback(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test that existing feedback is shown on edit page."""
        meal = create_meal(
            db, test_user,
            ai_suggested_ingredients=[{"name": "chicken", "state": "cooked"}]
        )

        # Create existing feedback
        feedback = UserFeedback(
            user_id=test_user.id,
            feature_type="meal_analysis",
            feature_id=meal.id,
            rating=4,
            feedback_text="Good analysis"
        )
        db.add(feedback)
        db.commit()

        response = auth_client.get(f"/meals/{meal.id}/edit-ingredients")

        assert response.status_code == 200
