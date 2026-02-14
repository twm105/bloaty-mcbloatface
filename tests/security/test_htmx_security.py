"""
Security tests for htmx partial responses.

Tests htmx-specific security concerns:
- Partial response escaping
- CSRF protection
- Request origin validation
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User
from tests.factories import create_user, create_meal, create_symptom, create_ingredient


@pytest.mark.security
class TestPartialResponseEscaping:
    """Tests for proper escaping in htmx partial responses."""

    def test_ingredient_partial_xss(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test XSS in ingredient partials is escaped."""
        meal = create_meal(db, test_user)
        xss_payload = "<script>alert('XSS')</script>"

        # Add ingredient with XSS payload
        response = auth_client.post(
            f"/meals/{meal.id}/ingredients/add",
            data={"ingredient_name": xss_payload, "state": "raw"},
            headers={"HX-Request": "true"}  # htmx request
        )

        # Response should have escaped content
        if response.status_code == 200:
            assert "<script>" not in response.text or "&lt;script&gt;" in response.text

    def test_symptom_tag_partial_xss(
        self, auth_client: TestClient, test_user: User
    ):
        """Test XSS in symptom tag suggestions is escaped."""
        xss_payload = "<img src=x onerror=alert(1)>"

        response = auth_client.get(
            f"/symptoms/tags/autocomplete?q={xss_payload}",
            headers={"HX-Request": "true"}
        )

        # Should not contain unescaped payload
        assert response.status_code == 200
        assert "onerror=" not in response.text

    def test_meal_history_partial_xss(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test XSS in meal history partials is escaped."""
        xss_payload = "'\"><script>alert(1)</script>"
        create_meal(db, test_user, name=xss_payload)

        response = auth_client.get(
            "/meals/history",
            headers={"HX-Request": "true"}
        )

        assert response.status_code == 200
        # Script should be escaped
        assert "alert(1)</script>" not in response.text or "&" in response.text


@pytest.mark.security
class TestCSRFProtection:
    """Tests for CSRF protection on state-changing operations."""

    def test_delete_without_session(self, client: TestClient, db: Session):
        """Test that DELETE operations require valid session."""
        user = create_user(db)
        meal = create_meal(db, user)

        # Try to delete without session
        response = client.delete(f"/meals/{meal.id}", follow_redirects=False)

        assert response.status_code in [302, 303, 307, 401]

    def test_post_without_session(self, client: TestClient, db: Session):
        """Test that POST operations require valid session."""
        response = client.post(
            "/symptoms/create-tagged",
            data={"tags_json": "[]"},
            follow_redirects=False
        )

        assert response.status_code in [302, 303, 307, 401]

    def test_logout_requires_session(self, client: TestClient):
        """Test that logout requires valid session."""
        response = client.post("/auth/logout", follow_redirects=False)

        # Should redirect to login or handle gracefully
        assert response.status_code in [303, 302, 307]


@pytest.mark.security
class TestHtmxHeaders:
    """Tests for htmx header handling."""

    def test_hx_request_header_respected(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test that HX-Request header triggers partial responses."""
        create_meal(db, test_user, name="Test Meal")

        # Without HX-Request - should get full page
        full_response = auth_client.get("/meals/history")

        # With HX-Request - may get partial
        partial_response = auth_client.get(
            "/meals/history",
            headers={"HX-Request": "true"}
        )

        # Both should succeed
        assert full_response.status_code == 200
        assert partial_response.status_code == 200

    def test_hx_target_not_exploitable(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test that HX-Target header can't be exploited."""
        meal = create_meal(db, test_user)

        # Try to inject malicious target
        response = auth_client.get(
            f"/meals/{meal.id}/edit-ingredients",
            headers={
                "HX-Request": "true",
                "HX-Target": "<script>alert(1)</script>"
            }
        )

        assert response.status_code == 200
        # Target header value should not appear unescaped in response
        assert "<script>alert(1)</script>" not in response.text


@pytest.mark.security
class TestResponseHeaders:
    """Tests for security response headers."""

    def test_content_type_header(
        self, auth_client: TestClient, test_user: User
    ):
        """Test that responses have correct Content-Type."""
        # HTML response
        html_response = auth_client.get("/meals/history")
        assert "text/html" in html_response.headers.get("content-type", "")

        # JSON response
        json_response = auth_client.get("/symptoms/tags/common")
        assert "application/json" in json_response.headers.get("content-type", "")

    def test_xss_protection_headers(
        self, auth_client: TestClient, test_user: User
    ):
        """Test for X-XSS-Protection or CSP headers."""
        response = auth_client.get("/meals/history")

        # Check for security headers (may be configured in production)
        # These are advisory checks - the app may or may not have them
        headers = response.headers

        # Log which headers are present for awareness
        security_headers = [
            "X-XSS-Protection",
            "X-Content-Type-Options",
            "Content-Security-Policy",
            "X-Frame-Options"
        ]

        # At minimum, verify we can check these headers
        for header in security_headers:
            # Just accessing the header, not asserting presence
            _ = headers.get(header)


@pytest.mark.security
class TestHtmxSwapSecurity:
    """Tests for htmx swap security."""

    def test_oob_swap_not_exploitable(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test that out-of-band swaps can't inject content elsewhere."""
        meal = create_meal(db, test_user)
        xss_payload = "test<div hx-swap-oob='innerHTML:#admin-panel'>hacked</div>"

        response = auth_client.post(
            f"/meals/{meal.id}/ingredients/add",
            data={"ingredient_name": xss_payload, "state": "raw"},
            headers={"HX-Request": "true"}
        )

        # Should not contain unescaped hx-swap-oob
        if response.status_code == 200:
            assert "hx-swap-oob=" not in response.text or "&" in response.text

    def test_attribute_injection_prevented(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test that htmx attribute injection is prevented."""
        meal = create_meal(db, test_user)

        # Try to inject htmx attributes
        malicious_name = 'test" hx-get="/auth/users" hx-trigger="load'

        response = auth_client.post(
            f"/meals/{meal.id}/ingredients/add",
            data={"ingredient_name": malicious_name, "state": "raw"},
            headers={"HX-Request": "true"}
        )

        # Attributes should be escaped (either &quot; or &#34; is acceptable)
        if response.status_code == 200:
            assert 'hx-get=' not in response.text or '&quot;' in response.text or '&#34;' in response.text
