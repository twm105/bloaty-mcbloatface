"""
Tests for meal search functionality.
"""

import secrets
from sqlalchemy.orm import Session

from app.services.meal_service import meal_service
from tests.factories import create_user, create_meal


class TestSearchUserMeals:
    """Tests for MealService.search_user_meals()."""

    def test_search_returns_matching_meals(self, db: Session):
        """Search should return meals matching the query by name."""
        user = create_user(db)
        # Use unique names to avoid collisions with other tests
        suffix = secrets.token_hex(4)
        create_meal(db, user, name=f"Spaghetti Carbonara {suffix}")
        create_meal(db, user, name=f"Pizza Margherita {suffix}")
        create_meal(db, user, name=f"Spaghetti Bolognese {suffix}")

        results = meal_service.search_user_meals(db, user.id, "Spaghetti")

        assert len(results) == 2
        names = [r.name for r in results]
        assert f"Spaghetti Carbonara {suffix}" in names
        assert f"Spaghetti Bolognese {suffix}" in names

    def test_search_is_case_insensitive(self, db: Session):
        """Search should be case-insensitive."""
        user = create_user(db)
        suffix = secrets.token_hex(4)
        create_meal(db, user, name=f"PIZZA Margherita {suffix}")
        create_meal(db, user, name=f"pizza napoletana {suffix}")

        # Search with mixed case
        results = meal_service.search_user_meals(db, user.id, "PiZzA")

        assert len(results) == 2

    def test_search_returns_partial_matches(self, db: Session):
        """Search should return partial matches."""
        user = create_user(db)
        suffix = secrets.token_hex(4)
        create_meal(db, user, name=f"Homemade Pasta {suffix}")
        create_meal(db, user, name=f"Pasta Salad {suffix}")
        create_meal(db, user, name=f"Fresh Pasta Primavera {suffix}")

        results = meal_service.search_user_meals(db, user.id, "pasta")

        assert len(results) == 3

    def test_search_only_returns_published_meals(self, db: Session):
        """Search should only return published meals, not drafts."""
        user = create_user(db)
        suffix = secrets.token_hex(4)
        create_meal(db, user, name=f"Published Meal {suffix}", status="published")
        create_meal(db, user, name=f"Draft Meal {suffix}", status="draft")

        results = meal_service.search_user_meals(db, user.id, "Meal")

        assert len(results) == 1
        assert results[0].name == f"Published Meal {suffix}"
        assert results[0].status == "published"

    def test_search_empty_query_returns_all_meals(self, db: Session):
        """Empty query should return all published meals."""
        user = create_user(db)
        suffix = secrets.token_hex(4)
        create_meal(db, user, name=f"Meal One {suffix}")
        create_meal(db, user, name=f"Meal Two {suffix}")
        create_meal(db, user, name=f"Meal Three {suffix}")

        results = meal_service.search_user_meals(db, user.id, "")

        assert len(results) >= 3

    def test_search_whitespace_query_returns_all_meals(self, db: Session):
        """Whitespace-only query should return all published meals."""
        user = create_user(db)
        suffix = secrets.token_hex(4)
        create_meal(db, user, name=f"Test Meal {suffix}")

        results = meal_service.search_user_meals(db, user.id, "   ")

        assert len(results) >= 1

    def test_search_only_returns_user_meals(self, db: Session):
        """Search should only return meals belonging to the specified user."""
        user1 = create_user(db, email="user1_search@example.com")
        user2 = create_user(db, email="user2_search@example.com")
        suffix = secrets.token_hex(4)

        create_meal(db, user1, name=f"User1 Pizza {suffix}")
        create_meal(db, user2, name=f"User2 Pizza {suffix}")

        results = meal_service.search_user_meals(db, user1.id, "Pizza")

        assert len(results) == 1
        assert results[0].name == f"User1 Pizza {suffix}"

    def test_search_orders_by_timestamp_descending(self, db: Session):
        """Results should be ordered by timestamp descending (newest first)."""
        from datetime import datetime, timedelta, timezone

        user = create_user(db)
        suffix = secrets.token_hex(4)
        now = datetime.now(timezone.utc)

        oldest = create_meal(
            db, user, name=f"Old Burger {suffix}", timestamp=now - timedelta(days=7)
        )
        middle = create_meal(
            db, user, name=f"Middle Burger {suffix}", timestamp=now - timedelta(days=3)
        )
        newest = create_meal(
            db, user, name=f"New Burger {suffix}", timestamp=now
        )

        results = meal_service.search_user_meals(db, user.id, "Burger")

        assert len(results) == 3
        assert results[0].id == newest.id
        assert results[1].id == middle.id
        assert results[2].id == oldest.id

    def test_search_respects_limit(self, db: Session):
        """Search should respect the limit parameter."""
        user = create_user(db)
        suffix = secrets.token_hex(4)
        for i in range(10):
            create_meal(db, user, name=f"Test Meal {i} {suffix}")

        results = meal_service.search_user_meals(db, user.id, "Test Meal", limit=5)

        assert len(results) == 5

    def test_search_no_matches_returns_empty_list(self, db: Session):
        """Search with no matches should return an empty list."""
        user = create_user(db)
        suffix = secrets.token_hex(4)
        create_meal(db, user, name=f"Spaghetti {suffix}")

        results = meal_service.search_user_meals(db, user.id, "NonexistentMeal12345")

        assert len(results) == 0


class TestSearchEndpoint:
    """Tests for the /meals/history/results endpoint."""

    def test_search_endpoint_requires_auth(self, client):
        """Search endpoint should require authentication."""
        response = client.get("/meals/history/results?q=pizza")

        # Should redirect to login
        assert response.status_code in [302, 303, 307, 401]

    def test_search_endpoint_returns_html(self, auth_client, db: Session, test_user):
        """Search endpoint should return HTML partial."""
        suffix = secrets.token_hex(4)
        create_meal(db, test_user, name=f"Test Pizza {suffix}")

        response = auth_client.get(f"/meals/history/results?q=Pizza {suffix}")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        # Should contain the meal card
        assert f"Test Pizza {suffix}" in response.text

    def test_search_endpoint_empty_query(self, auth_client, db: Session, test_user):
        """Empty query should return all meals."""
        suffix = secrets.token_hex(4)
        create_meal(db, test_user, name=f"Meal A {suffix}")
        create_meal(db, test_user, name=f"Meal B {suffix}")

        response = auth_client.get("/meals/history/results?q=")

        assert response.status_code == 200
        # Should contain both meals
        assert f"Meal A {suffix}" in response.text or f"Meal B {suffix}" in response.text

    def test_search_endpoint_no_results_message(self, auth_client, db: Session, test_user):
        """No results should show appropriate message."""
        response = auth_client.get("/meals/history/results?q=NonexistentFood12345")

        assert response.status_code == 200
        assert "No meals found" in response.text

    def test_history_page_has_search_bar(self, auth_client):
        """History page should include the search bar."""
        response = auth_client.get("/meals/history")

        assert response.status_code == 200
        # Check for search input
        assert 'name="q"' in response.text
        assert 'placeholder="Search meals..."' in response.text

    def test_history_page_search_active_autofocus(self, auth_client):
        """History page with search=1 should have autofocus on search."""
        response = auth_client.get("/meals/history?search=1")

        assert response.status_code == 200
        assert "autofocus" in response.text

    def test_history_page_has_clear_button(self, auth_client):
        """History page should include the search clear button."""
        response = auth_client.get("/meals/history")

        assert response.status_code == 200
        assert "search-clear-btn" in response.text

    def test_empty_query_returns_day_grouped_view(self, auth_client, db: Session, test_user):
        """Empty query should return day-grouped HTML template."""
        suffix = secrets.token_hex(4)
        create_meal(db, test_user, name=f"Test Meal {suffix}")

        response = auth_client.get("/meals/history/results?q=")

        assert response.status_code == 200
        # Day-grouped view uses the grouped template with recent-meals-grid element
        assert 'id="recent-meals-grid"' in response.text

    def test_whitespace_query_returns_day_grouped_view(self, auth_client, db: Session, test_user):
        """Whitespace-only query should return day-grouped HTML."""
        suffix = secrets.token_hex(4)
        create_meal(db, test_user, name=f"Test Meal {suffix}")

        response = auth_client.get("/meals/history/results?q=   ")

        assert response.status_code == 200
        # Should use day-grouped template (contains recent-meals-grid)
        assert "recent-meals-grid" in response.text

    def test_search_query_returns_flat_results(self, auth_client, db: Session, test_user):
        """Non-empty search query should return flat results without day grouping."""
        from datetime import datetime, timedelta, timezone

        suffix = secrets.token_hex(4)
        now = datetime.now(timezone.utc)
        # Create meals on different days
        create_meal(db, test_user, name=f"SearchTest {suffix} Today", timestamp=now)
        create_meal(
            db, test_user, name=f"SearchTest {suffix} Yesterday", timestamp=now - timedelta(days=1)
        )

        response = auth_client.get(f"/meals/history/results?q={suffix}")

        assert response.status_code == 200
        # Flat results should NOT contain day-section or the actual recent-meals-grid element
        assert "day-section" not in response.text
        assert 'id="recent-meals-grid"' not in response.text
        # But should contain the meals
        assert f"SearchTest {suffix} Today" in response.text
        assert f"SearchTest {suffix} Yesterday" in response.text

    def test_search_results_have_card_grid_id(self, auth_client, db: Session, test_user):
        """Search results should have a card-grid with ID for duplicate button targeting."""
        suffix = secrets.token_hex(4)
        create_meal(db, test_user, name=f"DuplicateTest {suffix}")

        response = auth_client.get(f"/meals/history/results?q={suffix}")

        assert response.status_code == 200
        # Search results use meal_cards.html which has search-results-grid ID
        assert 'id="search-results-grid"' in response.text
        # Verify the card-grid class is present (used by hx-target="closest .card-grid")
        assert 'class="card-grid"' in response.text

    def test_duplicate_button_uses_closest_card_grid(self, auth_client, db: Session, test_user):
        """Duplicate button should target closest .card-grid, not a specific ID."""
        suffix = secrets.token_hex(4)
        create_meal(db, test_user, name=f"DuplicateBtnTest {suffix}")

        response = auth_client.get(f"/meals/history/results?q={suffix}")

        assert response.status_code == 200
        # The duplicate button should use "closest .card-grid" as target
        assert 'hx-target="closest .card-grid"' in response.text

    def test_history_page_with_q_returns_full_page_with_results(
        self, auth_client, db: Session, test_user
    ):
        """Navigating to /meals/history?q=... should return full page with search results."""
        suffix = secrets.token_hex(4)
        create_meal(db, test_user, name=f"FullPageSearch {suffix}")
        create_meal(db, test_user, name=f"OtherMeal {suffix}")

        response = auth_client.get(f"/meals/history?q=FullPageSearch")

        assert response.status_code == 200
        # Should be a full HTML page (not a partial)
        assert "<!DOCTYPE html>" in response.text or "<html" in response.text
        assert "<head>" in response.text
        assert "Meal History" in response.text
        # Should contain the matching meal
        assert f"FullPageSearch {suffix}" in response.text
        # Search input should be pre-filled
        assert 'x-data="{ searchQuery: \'FullPageSearch\' }"' in response.text

    def test_history_page_with_q_shows_flat_results(
        self, auth_client, db: Session, test_user
    ):
        """History page with q param should show flat results, not day-grouped."""
        suffix = secrets.token_hex(4)
        create_meal(db, test_user, name=f"FlatResultsTest {suffix}")

        response = auth_client.get(f"/meals/history?q={suffix}")

        assert response.status_code == 200
        # Should use flat search results (search-results-grid), not day-grouped (recent-meals-grid)
        assert 'id="search-results-grid"' in response.text
        assert 'id="recent-meals-grid"' not in response.text

    def test_results_endpoint_sets_hx_push_url_header(
        self, auth_client, db: Session, test_user
    ):
        """Results endpoint should set HX-Push-Url header for browser history."""
        suffix = secrets.token_hex(4)
        create_meal(db, test_user, name=f"PushUrlTest {suffix}")

        response = auth_client.get(f"/meals/history/results?q={suffix}")

        assert response.status_code == 200
        # Should have HX-Push-Url header pointing to full page URL
        assert "HX-Push-Url" in response.headers
        assert response.headers["HX-Push-Url"] == f"/meals/history?q={suffix}"

    def test_results_endpoint_empty_query_pushes_base_url(
        self, auth_client, db: Session, test_user
    ):
        """Empty query should push base history URL without q param."""
        response = auth_client.get("/meals/history/results?q=")

        assert response.status_code == 200
        # Should have HX-Push-Url header pointing to base URL
        assert "HX-Push-Url" in response.headers
        assert response.headers["HX-Push-Url"] == "/meals/history"
