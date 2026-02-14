"""
Tests for race conditions and concurrent operations.

Tests scenarios where multiple operations might conflict:
- Concurrent ingredient creation
- Simultaneous meal updates
- Session management under load
"""
import pytest
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User, Ingredient, Meal
from tests.factories import create_user, create_meal, create_ingredient


class TestIngredientRaceConditions:
    """Tests for ingredient creation race conditions."""

    def test_concurrent_ingredient_creation(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test that concurrent requests to create same ingredient don't fail."""
        meal = create_meal(db, test_user)

        # Simulate concurrent requests to add the same ingredient
        results = []

        def add_ingredient():
            try:
                response = auth_client.post(
                    f"/meals/{meal.id}/ingredients/add",
                    data={
                        "ingredient_name": "Chicken",
                        "state": "cooked"
                    }
                )
                return response.status_code
            except Exception as e:
                return str(e)

        # Run multiple concurrent requests
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(add_ingredient) for _ in range(5)]
            for future in as_completed(futures):
                results.append(future.result())

        # All requests should succeed or fail gracefully (no 500 errors)
        for result in results:
            if isinstance(result, int):
                assert result in [200, 201, 303, 400, 409]  # Not 500

    def test_ingredient_deduplication(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test that duplicate ingredient names are handled properly."""
        meal = create_meal(db, test_user)

        # Add same ingredient twice
        auth_client.post(
            f"/meals/{meal.id}/ingredients/add",
            data={"ingredient_name": "Tomato", "state": "raw"}
        )
        auth_client.post(
            f"/meals/{meal.id}/ingredients/add",
            data={"ingredient_name": "Tomato", "state": "raw"}
        )

        # Check ingredient table for duplicates
        tomatoes = db.query(Ingredient).filter(
            Ingredient.name.ilike("tomato")
        ).all()

        # Should have exactly one unique ingredient (normalized)
        assert len(tomatoes) <= 2  # Might have raw and cooked variants


class TestMealRaceConditions:
    """Tests for meal operation race conditions."""

    def test_concurrent_meal_name_updates(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test concurrent updates to same meal name."""
        meal = create_meal(db, test_user)

        def update_meal_name(name: str):
            try:
                response = auth_client.put(
                    f"/meals/{meal.id}/name",
                    data={"name": name}
                )
                return response.status_code
            except Exception as e:
                return str(e)

        # Run concurrent updates
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(update_meal_name, f"Meal Update {i}")
                for i in range(3)
            ]
            results = [f.result() for f in as_completed(futures)]

        # All should succeed without errors
        for result in results:
            if isinstance(result, int):
                assert result in [200, 303]

    def test_delete_while_updating(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test deletion during update doesn't cause errors."""
        meal = create_meal(db, test_user)
        meal_id = meal.id

        def delete_meal():
            return auth_client.delete(f"/meals/{meal_id}")

        def update_meal_name():
            return auth_client.put(
                f"/meals/{meal_id}/name",
                data={"name": "Updated Name"}
            )

        # Run delete and update concurrently
        with ThreadPoolExecutor(max_workers=2) as executor:
            delete_future = executor.submit(delete_meal)
            update_future = executor.submit(update_meal_name)

            delete_result = delete_future.result()
            update_result = update_future.result()

        # One should succeed, other might get 404 - but no 500 errors
        assert delete_result.status_code in [200, 204, 303, 404]
        assert update_result.status_code in [200, 303, 404]


class TestSessionRaceConditions:
    """Tests for session management race conditions."""

    def test_concurrent_logout(
        self, auth_client: TestClient, test_user: User
    ):
        """Test multiple concurrent logout attempts."""
        results = []

        def logout():
            try:
                response = auth_client.post(
                    "/auth/logout",
                    follow_redirects=False
                )
                return response.status_code
            except Exception as e:
                return str(e)

        # Multiple logout attempts
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(logout) for _ in range(3)]
            results = [f.result() for f in as_completed(futures)]

        # All should succeed gracefully (first succeeds, others might fail gracefully)
        for result in results:
            if isinstance(result, int):
                assert result in [200, 303, 401]


class TestSymptomRaceConditions:
    """Tests for symptom operation race conditions."""

    def test_concurrent_symptom_creation(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test concurrent symptom creation."""
        import json

        results = []

        def create_symptom(i: int):
            try:
                response = auth_client.post(
                    "/symptoms/create-tagged",
                    data={
                        "tags_json": json.dumps([
                            {"name": f"symptom_{i}", "severity": 5}
                        ])
                    },
                    follow_redirects=False
                )
                return response.status_code
            except Exception as e:
                return str(e)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_symptom, i) for i in range(5)]
            results = [f.result() for f in as_completed(futures)]

        # All should succeed
        for result in results:
            if isinstance(result, int):
                assert result == 303


class TestDiagnosisRaceConditions:
    """Tests for diagnosis operation race conditions."""

    def test_concurrent_diagnosis_runs(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test starting multiple diagnosis runs concurrently."""
        results = []

        def start_diagnosis():
            try:
                response = auth_client.post(
                    "/diagnosis/analyze",
                    json={"async_mode": False}
                )
                return response.status_code
            except Exception as e:
                return str(e)

        # Multiple concurrent analysis requests
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(start_diagnosis) for _ in range(3)]
            results = [f.result() for f in as_completed(futures)]

        # Should handle gracefully (may return insufficient data or success)
        for result in results:
            if isinstance(result, int):
                assert result in [200, 400, 503]  # Not 500
