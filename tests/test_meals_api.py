"""
Tests for Meals API endpoints - specifically the duplicate endpoint.
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.meal_ingredient import IngredientState
from tests.factories import (
    create_user,
    create_meal,
    create_ingredient,
    create_meal_ingredient,
)


class TestDuplicateMealEndpoint:
    """Tests for POST /meals/{meal_id}/duplicate."""

    def test_duplicate_meal_returns_html_partial(
        self, db: Session, auth_client: TestClient, test_user
    ):
        """Verify returns meal card HTML."""
        meal = create_meal(
            db,
            test_user,
            name="Test Meal to Duplicate",
            country="Japan",
            image_path="uploads/test.jpg",  # Need image for badge-copy to show
        )
        tomato = create_ingredient(db, name="Tomato")
        create_meal_ingredient(db, meal, tomato, state=IngredientState.RAW)
        db.refresh(meal)

        response = auth_client.post(f"/meals/{meal.id}/duplicate")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        # Check the response contains the meal card structure
        assert "meal-card" in response.text
        assert "Test Meal to Duplicate" in response.text
        # Should have the copy badge (only shown when meal has image)
        assert "badge-copy" in response.text

    def test_duplicate_meal_unauthorized(self, client: TestClient, db: Session):
        """Verify 401 without auth."""
        user = create_user(db)
        meal = create_meal(db, user, name="Test Meal")

        response = client.post(f"/meals/{meal.id}/duplicate")

        # Should redirect to login or return 401/403
        assert response.status_code in [401, 302, 303]

    def test_duplicate_meal_forbidden(
        self, db: Session, auth_client: TestClient, test_user
    ):
        """Verify 403 for another user's meal."""
        other_user = create_user(db, email="other@example.com")
        other_meal = create_meal(db, other_user, name="Other User's Meal")

        response = auth_client.post(f"/meals/{other_meal.id}/duplicate")

        assert response.status_code == 403

    def test_duplicate_meal_not_found(self, auth_client: TestClient):
        """Verify 404 for non-existent meal."""
        response = auth_client.post("/meals/999999/duplicate")

        assert response.status_code == 404

    def test_duplicate_meal_creates_copy_in_database(
        self, db: Session, auth_client: TestClient, test_user
    ):
        """Verify the duplicate is actually created in the database."""
        original = create_meal(db, test_user, name="Original Meal", country="USA")
        tomato = create_ingredient(db, name="Tomato")
        create_meal_ingredient(
            db, original, tomato, state=IngredientState.COOKED, quantity_description="2"
        )
        db.refresh(original)

        response = auth_client.post(f"/meals/{original.id}/duplicate")
        assert response.status_code == 200

        # Verify the new meal exists in the database
        from app.models.meal import Meal

        meals = db.query(Meal).filter(Meal.user_id == test_user.id).all()
        assert len(meals) == 2

        new_meal = next(m for m in meals if m.id != original.id)
        assert new_meal.name == original.name
        assert new_meal.country == original.country
        assert new_meal.copied_from_id == original.id
        assert new_meal.status == "published"
        assert len(new_meal.meal_ingredients) == 1
        assert new_meal.meal_ingredients[0].source == "copy"

    def test_duplicate_meal_htmx_headers(
        self, db: Session, auth_client: TestClient, test_user
    ):
        """Verify endpoint works correctly with htmx headers."""
        meal = create_meal(db, test_user, name="Test Meal")

        # Simulate htmx request
        response = auth_client.post(
            f"/meals/{meal.id}/duplicate",
            headers={
                "HX-Request": "true",
                "HX-Target": "recent-meals-grid",
            },
        )

        assert response.status_code == 200
        assert "meal-card" in response.text
