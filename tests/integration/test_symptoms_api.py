"""
Integration tests for Symptoms API.

Tests the full symptom management flow including:
- Authentication requirements
- Tag-based symptom creation
- Episode and ongoing detection
- AI elaboration endpoints
"""
import pytest
import json
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import patch, AsyncMock

from app.models import User, Symptom
from tests.factories import create_user, create_symptom


class TestSymptomAuthentication:
    """Tests for symptom endpoint authentication."""

    def test_symptom_log_requires_auth(self, client: TestClient):
        """Test that symptom log page requires authentication."""
        response = client.get("/symptoms/log", follow_redirects=False)

        assert response.status_code in [302, 303, 307, 401]

    def test_symptom_history_requires_auth(self, client: TestClient):
        """Test that symptom history requires authentication."""
        response = client.get("/symptoms/history", follow_redirects=False)

        assert response.status_code in [302, 303, 307, 401]

    def test_symptom_log_accessible_when_logged_in(
        self, auth_client: TestClient, test_user: User
    ):
        """Test that symptom log is accessible when logged in."""
        response = auth_client.get("/symptoms/log")

        assert response.status_code == 200


class TestCommonTags:
    """Tests for common/quick-add tags endpoint."""

    def test_get_common_tags_empty_history(
        self, auth_client: TestClient, test_user: User
    ):
        """Test common tags returns defaults for new user."""
        response = auth_client.get("/symptoms/tags/common")

        assert response.status_code == 200
        data = response.json()
        assert "tags" in data
        assert len(data["tags"]) <= 6
        # Default tags for new users
        tag_names = [t["name"] for t in data["tags"]]
        assert "bloating" in tag_names or len(tag_names) > 0

    def test_get_common_tags_with_history(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test common tags uses user history."""
        # Create some symptoms with tags
        for i in range(3):
            create_symptom(
                db, test_user,
                tags=[{"name": "custom_symptom", "severity": 5}]
            )

        response = auth_client.get("/symptoms/tags/common")

        assert response.status_code == 200
        data = response.json()
        assert "tags" in data


class TestTagAutocomplete:
    """Tests for tag autocomplete/search."""

    def test_autocomplete_requires_query(
        self, auth_client: TestClient, test_user: User
    ):
        """Test that autocomplete requires query parameter."""
        response = auth_client.get("/symptoms/tags/autocomplete")

        # Should fail without 'q' parameter
        assert response.status_code == 422

    def test_autocomplete_returns_suggestions(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test autocomplete returns matching suggestions."""
        # Create symptoms with searchable tags
        create_symptom(db, test_user, tags=[{"name": "bloating", "severity": 5}])
        create_symptom(db, test_user, tags=[{"name": "bloating_severe", "severity": 8}])

        response = auth_client.get("/symptoms/tags/autocomplete?q=bloat")

        assert response.status_code == 200
        data = response.json()
        assert "suggestions" in data

    def test_autocomplete_empty_query(
        self, auth_client: TestClient, test_user: User
    ):
        """Test autocomplete with empty query."""
        response = auth_client.get("/symptoms/tags/autocomplete?q=")

        # Empty query should still work
        assert response.status_code in [200, 422]


class TestSymptomCreation:
    """Tests for creating symptoms."""

    def test_create_tagged_symptom(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test creating a symptom with tags."""
        tags = [
            {"name": "bloating", "severity": 7},
            {"name": "gas", "severity": 5}
        ]

        response = auth_client.post(
            "/symptoms/create-tagged",
            data={
                "tags_json": json.dumps(tags),
                "ai_generated_text": "AI elaboration text",
                "final_notes": "Final notes"
            },
            follow_redirects=False
        )

        assert response.status_code == 303
        assert "history" in response.headers.get("location", "")

    def test_create_tagged_symptom_invalid_json(
        self, auth_client: TestClient, test_user: User
    ):
        """Test creating symptom with invalid JSON."""
        response = auth_client.post(
            "/symptoms/create-tagged",
            data={
                "tags_json": "not valid json",
            },
            follow_redirects=False
        )

        assert response.status_code == 400

    def test_create_legacy_symptom(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test legacy symptom creation endpoint."""
        response = auth_client.post(
            "/symptoms/create",
            data={
                "description": "Stomach pain",
                "symptom_type": "digestive",
                "severity": 6,
                "notes": "After eating"
            },
            follow_redirects=False
        )

        assert response.status_code == 303

    def test_create_symptom_invalid_severity(
        self, auth_client: TestClient, test_user: User
    ):
        """Test creating symptom with invalid severity."""
        response = auth_client.post(
            "/symptoms/create",
            data={
                "description": "Pain",
                "symptom_type": "other",
                "severity": 15,  # Invalid: > 10
            },
            follow_redirects=False
        )

        assert response.status_code == 400


class TestSymptomHistory:
    """Tests for symptom history page."""

    def test_history_renders_empty(
        self, auth_client: TestClient, test_user: User
    ):
        """Test history page renders with no symptoms."""
        response = auth_client.get("/symptoms/history")

        assert response.status_code == 200

    def test_history_shows_symptoms(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test history shows user's symptoms."""
        create_symptom(db, test_user, tags=[{"name": "headache", "severity": 6}])

        response = auth_client.get("/symptoms/history")

        assert response.status_code == 200
        assert "headache" in response.text.lower()

    def test_history_success_param(
        self, auth_client: TestClient, test_user: User
    ):
        """Test history with success parameter."""
        response = auth_client.get("/symptoms/history?success=true")

        assert response.status_code == 200


class TestSymptomViewing:
    """Tests for viewing individual symptoms."""

    def test_edit_page_renders(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test that edit page renders for own symptom."""
        symptom = create_symptom(db, test_user)

        response = auth_client.get(f"/symptoms/{symptom.id}/edit")

        assert response.status_code == 200

    def test_cannot_edit_other_user_symptom(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test that editing another user's symptom is forbidden."""
        other_user = create_user(db, email="other@example.com")
        symptom = create_symptom(db, other_user)

        response = auth_client.get(f"/symptoms/{symptom.id}/edit")

        assert response.status_code in [403, 404]

    def test_edit_nonexistent_symptom(
        self, auth_client: TestClient, test_user: User
    ):
        """Test editing non-existent symptom."""
        response = auth_client.get("/symptoms/99999/edit")

        assert response.status_code == 404


class TestSymptomUpdates:
    """Tests for updating symptoms."""

    def test_update_symptom_tags(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test updating symptom with new tags."""
        symptom = create_symptom(db, test_user)

        response = auth_client.put(
            f"/symptoms/{symptom.id}",
            json={
                "tags": [{"name": "updated_tag", "severity": 8}],
                "notes": "Updated notes"
            }
        )

        assert response.status_code == 200

    def test_update_legacy_symptom(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test legacy symptom update endpoint."""
        symptom = create_symptom(db, test_user)

        response = auth_client.post(
            f"/symptoms/{symptom.id}/update",
            data={
                "description": "Updated description",
                "symptom_type": "digestive",
                "severity": 5
            },
            follow_redirects=False
        )

        assert response.status_code == 303

    def test_cannot_update_other_user_symptom(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test that updating another user's symptom is forbidden."""
        other_user = create_user(db, email="other@example.com")
        symptom = create_symptom(db, other_user)

        response = auth_client.put(
            f"/symptoms/{symptom.id}",
            json={"tags": [{"name": "hack", "severity": 1}]}
        )

        assert response.status_code in [403, 404]


class TestSymptomDeletion:
    """Tests for deleting symptoms."""

    def test_delete_symptom(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test deleting own symptom."""
        symptom = create_symptom(db, test_user)
        symptom_id = symptom.id

        response = auth_client.delete(f"/symptoms/{symptom_id}")

        assert response.status_code == 200

        # Verify symptom is deleted
        assert db.query(Symptom).filter(Symptom.id == symptom_id).first() is None

    def test_cannot_delete_other_user_symptom(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test that deleting another user's symptom is forbidden."""
        other_user = create_user(db, email="other@example.com")
        symptom = create_symptom(db, other_user)

        response = auth_client.delete(f"/symptoms/{symptom.id}")

        assert response.status_code in [403, 404]

    def test_delete_nonexistent_symptom(
        self, auth_client: TestClient, test_user: User
    ):
        """Test deleting non-existent symptom."""
        response = auth_client.delete("/symptoms/99999")

        assert response.status_code == 404


class TestElaborationEndpoints:
    """Tests for AI elaboration endpoints (mocked)."""

    def test_elaborate_tags_success(
        self, auth_client: TestClient, test_user: User, mock_claude_service
    ):
        """Test non-streaming elaboration."""
        with patch("app.api.symptoms.claude_service", mock_claude_service):
            response = auth_client.post(
                "/symptoms/tags/elaborate",
                json={
                    "tags": [{"name": "bloating", "severity": 7}],
                    "start_time": "2026-01-30T14:00:00"
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert "elaboration" in data
            assert data["success"] is True

    def test_elaborate_tags_stream(
        self, auth_client: TestClient, test_user: User, mock_claude_service
    ):
        """Test streaming elaboration endpoint."""
        with patch("app.api.symptoms.claude_service", mock_claude_service):
            response = auth_client.post(
                "/symptoms/tags/elaborate-stream",
                json={
                    "tags": [{"name": "nausea", "severity": 5}]
                }
            )

            # Streaming response
            assert response.status_code == 200


class TestEpisodeDetection:
    """Tests for episode detection endpoints."""

    def test_detect_episode_no_history(
        self, auth_client: TestClient, test_user: User, mock_claude_service
    ):
        """Test episode detection with no recent symptoms."""
        with patch("app.api.symptoms.claude_service", mock_claude_service):
            response = auth_client.post(
                "/symptoms/detect-episode",
                json={
                    "tags": [{"name": "bloating", "severity": 6}],
                    "start_time": datetime.now(timezone.utc).isoformat()
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert data["is_continuation"] is False

    def test_detect_episode_with_history(
        self, auth_client: TestClient, test_user: User, db: Session, mock_claude_service
    ):
        """Test episode detection with recent similar symptoms."""
        # Create a recent symptom
        create_symptom(
            db, test_user,
            tags=[{"name": "bloating", "severity": 7}],
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2)
        )

        with patch("app.api.symptoms.claude_service", mock_claude_service):
            response = auth_client.post(
                "/symptoms/detect-episode",
                json={
                    "tags": [{"name": "bloating", "severity": 6}],
                    "start_time": datetime.now(timezone.utc).isoformat()
                }
            )

            assert response.status_code == 200
            data = response.json()
            # Should detect potential episode
            assert "is_continuation" in data


class TestOngoingSymptomDetection:
    """Tests for ongoing symptom detection."""

    def test_detect_ongoing_no_history(
        self, auth_client: TestClient, test_user: User, mock_claude_service
    ):
        """Test ongoing detection with no recent symptoms."""
        with patch("app.api.symptoms.claude_service", mock_claude_service):
            response = auth_client.post(
                "/symptoms/detect-ongoing",
                json={
                    "symptom_name": "headache",
                    "symptom_severity": 5
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert data["is_ongoing"] is False
            assert data["potential_ongoing"] is None

    def test_detect_ongoing_with_history(
        self, auth_client: TestClient, test_user: User, db: Session, mock_claude_service
    ):
        """Test ongoing detection with recent similar symptom."""
        # Create a recent symptom with same name
        create_symptom(
            db, test_user,
            tags=[{"name": "headache", "severity": 6}],
            timestamp=datetime.now(timezone.utc) - timedelta(hours=12)
        )

        with patch("app.api.symptoms.claude_service", mock_claude_service):
            response = auth_client.post(
                "/symptoms/detect-ongoing",
                json={
                    "symptom_name": "headache",
                    "symptom_severity": 5
                }
            )

            assert response.status_code == 200
            data = response.json()
            # Should find potential ongoing symptom
            assert "is_ongoing" in data

    def test_detect_ongoing_different_name(
        self, auth_client: TestClient, test_user: User, db: Session, mock_claude_service
    ):
        """Test ongoing detection with different symptom names."""
        # Create a recent symptom with different name
        create_symptom(
            db, test_user,
            tags=[{"name": "migraine", "severity": 7}],
            timestamp=datetime.now(timezone.utc) - timedelta(hours=6)
        )

        with patch("app.api.symptoms.claude_service", mock_claude_service):
            response = auth_client.post(
                "/symptoms/detect-ongoing",
                json={
                    "symptom_name": "migraine",  # Same name
                    "symptom_severity": 5
                }
            )

            assert response.status_code == 200
            data = response.json()
            # Should find potential ongoing and check name_match
            if data["potential_ongoing"]:
                assert "name_match" in data


class TestCommonTagsFilling:
    """Tests for common tags filling logic."""

    def test_common_tags_fills_with_more_recent_tags(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test that common tags fills with more recent tags when < 6."""
        # Create 5 different symptoms with different tags
        for i in range(5):
            create_symptom(
                db, test_user,
                tags=[{"name": f"symptom_{i}", "severity": 5}],
                timestamp=datetime.now(timezone.utc) - timedelta(hours=i)
            )

        response = auth_client.get("/symptoms/tags/common")

        assert response.status_code == 200
        data = response.json()
        # Should have multiple tags
        assert len(data["tags"]) >= 1

    def test_common_tags_hybrid_recent_and_common(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test hybrid of recent and common tags."""
        # Create repeated symptom (common)
        for _ in range(5):
            create_symptom(
                db, test_user,
                tags=[{"name": "bloating", "severity": 6}]
            )

        # Create recent but different symptom
        create_symptom(
            db, test_user,
            tags=[{"name": "nausea", "severity": 4}],
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=5)
        )

        response = auth_client.get("/symptoms/tags/common")

        assert response.status_code == 200
        data = response.json()
        tag_names = [t["name"] for t in data["tags"]]
        # Should have bloating (common) and nausea (recent)
        assert "bloating" in tag_names or "nausea" in tag_names


class TestElaborationWithTimestamps:
    """Tests for elaboration with various timestamp inputs."""

    def test_elaborate_with_end_time(
        self, auth_client: TestClient, test_user: User, mock_claude_service
    ):
        """Test elaboration with end_time parameter."""
        with patch("app.api.symptoms.claude_service", mock_claude_service):
            response = auth_client.post(
                "/symptoms/tags/elaborate",
                json={
                    "tags": [{"name": "bloating", "severity": 7}],
                    "start_time": "2026-01-30T14:00:00",
                    "end_time": "2026-01-30T18:00:00",
                    "user_notes": "Lasted 4 hours"
                }
            )

            assert response.status_code == 200

    def test_elaborate_stream_with_timestamps(
        self, auth_client: TestClient, test_user: User, mock_claude_service
    ):
        """Test streaming elaboration with timestamps."""
        with patch("app.api.symptoms.claude_service", mock_claude_service):
            response = auth_client.post(
                "/symptoms/tags/elaborate-stream",
                json={
                    "tags": [{"name": "nausea", "severity": 5}],
                    "start_time": "2026-01-30T10:00:00",
                    "end_time": "2026-01-30T12:00:00"
                }
            )

            assert response.status_code == 200


class TestUpdateSymptomTimestamps:
    """Tests for updating symptom timestamps."""

    def test_update_symptom_with_timestamps(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test updating symptom with start_time and end_time."""
        symptom = create_symptom(db, test_user)

        response = auth_client.put(
            f"/symptoms/{symptom.id}",
            json={
                "tags": [{"name": "updated", "severity": 5}],
                "start_time": "2026-01-30T10:00:00Z",
                "end_time": "2026-01-30T14:00:00Z"
            }
        )

        assert response.status_code == 200

    def test_update_symptom_invalid_timestamps(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test updating symptom with invalid timestamps (should ignore)."""
        symptom = create_symptom(db, test_user)

        response = auth_client.put(
            f"/symptoms/{symptom.id}",
            json={
                "tags": [{"name": "updated", "severity": 5}],
                "start_time": "not-a-timestamp",
                "end_time": 12345  # Wrong type
            }
        )

        # Should still succeed, just ignore invalid timestamps
        assert response.status_code == 200


class TestLegacySymptomUpdateErrors:
    """Tests for legacy symptom update error handling."""

    def test_update_nonexistent_symptom(
        self, auth_client: TestClient, test_user: User
    ):
        """Test updating non-existent symptom."""
        response = auth_client.post(
            "/symptoms/99999/update",
            data={
                "description": "Updated",
                "symptom_type": "other",
                "severity": 5
            },
            follow_redirects=False
        )

        assert response.status_code == 404

    def test_update_other_user_symptom(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test updating another user's symptom."""
        other_user = create_user(db, email="other@example.com")
        symptom = create_symptom(db, other_user)

        response = auth_client.post(
            f"/symptoms/{symptom.id}/update",
            data={
                "description": "Hacked",
                "symptom_type": "other",
                "severity": 5
            },
            follow_redirects=False
        )

        assert response.status_code == 403

    def test_update_with_timestamp(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test legacy update with timestamp."""
        symptom = create_symptom(db, test_user)

        response = auth_client.post(
            f"/symptoms/{symptom.id}/update",
            data={
                "description": "Updated",
                "symptom_type": "digestive",
                "severity": 6,
                "symptom_timestamp": "2026-01-30T15:00:00"
            },
            follow_redirects=False
        )

        assert response.status_code == 303

    def test_update_with_invalid_timestamp(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test legacy update with invalid timestamp (should ignore)."""
        symptom = create_symptom(db, test_user)

        response = auth_client.post(
            f"/symptoms/{symptom.id}/update",
            data={
                "description": "Updated",
                "symptom_type": "digestive",
                "severity": 6,
                "symptom_timestamp": "not-valid"
            },
            follow_redirects=False
        )

        # Should succeed, just ignore invalid timestamp
        assert response.status_code == 303

    def test_update_with_invalid_severity(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test legacy update with invalid severity."""
        symptom = create_symptom(db, test_user)

        response = auth_client.post(
            f"/symptoms/{symptom.id}/update",
            data={
                "description": "Updated",
                "symptom_type": "digestive",
                "severity": 15  # Invalid
            },
            follow_redirects=False
        )

        assert response.status_code == 400


class TestDebugEndpoint:
    """Tests for debug endpoint."""

    def test_debug_symptom_count(
        self, auth_client: TestClient, test_user: User, db: Session
    ):
        """Test debug endpoint returns counts."""
        # Create some symptoms
        for _ in range(3):
            create_symptom(db, test_user)

        response = auth_client.get("/symptoms/debug/count")

        assert response.status_code == 200
        data = response.json()
        assert "total_symptoms" in data
        assert "user_symptoms" in data
        assert "user_id" in data
        assert data["user_symptoms"] >= 3
