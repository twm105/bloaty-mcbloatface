"""
Unit tests for SymptomService.

Tests the symptom business logic including:
- Tag-based symptom creation
- Episode detection and linking
- Similar symptom detection
- Tag search and autocomplete
"""
import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.services.symptom_service import SymptomService, symptom_service
from app.models import Symptom
from tests.factories import create_user, create_symptom, create_symptom_episode


class TestSymptomCreation:
    """Tests for symptom creation."""

    def test_create_symptom_basic(self, db: Session):
        """Test creating a basic symptom."""
        user = create_user(db)

        symptom = SymptomService.create_symptom(
            db, user.id,
            raw_description="I have a stomachache"
        )

        assert symptom.id is not None
        assert symptom.user_id == user.id
        assert symptom.raw_description == "I have a stomachache"

    def test_create_symptom_with_structured_data(self, db: Session):
        """Test creating a symptom with structured data."""
        user = create_user(db)

        symptom = SymptomService.create_symptom(
            db, user.id,
            raw_description="Stomach pain",
            structured_type="bloating",
            severity=7,
            notes="After eating lunch"
        )

        assert symptom.structured_type == "bloating"
        assert symptom.severity == 7
        assert symptom.notes == "After eating lunch"

    def test_create_symptom_with_timestamp(self, db: Session):
        """Test creating a symptom with custom timestamp."""
        user = create_user(db)
        custom_time = datetime.now(timezone.utc) - timedelta(hours=2)

        symptom = SymptomService.create_symptom(
            db, user.id,
            raw_description="Bloating",
            timestamp=custom_time
        )

        assert symptom.timestamp == custom_time


class TestSymptomWithTags:
    """Tests for tag-based symptom creation."""

    def test_create_symptom_with_tags(self, db: Session):
        """Test creating a symptom with tags."""
        user = create_user(db)
        tags = [
            {"name": "bloating", "severity": 7},
            {"name": "gas", "severity": 5}
        ]

        symptom = SymptomService.create_symptom_with_tags(
            db, user.id,
            tags=tags
        )

        assert symptom.id is not None
        assert symptom.tags == tags
        # Most severe tag should set structured_type
        assert symptom.structured_type == "bloating"
        assert symptom.severity == 7

    def test_create_symptom_with_tags_generates_description(self, db: Session):
        """Test that description is generated from tags."""
        user = create_user(db)
        tags = [{"name": "cramping", "severity": 6}]

        symptom = SymptomService.create_symptom_with_tags(
            db, user.id,
            tags=tags
        )

        assert "cramping" in symptom.raw_description.lower()
        assert "6/10" in symptom.raw_description

    def test_create_symptom_with_ai_text(self, db: Session):
        """Test creating a symptom with AI-generated text."""
        user = create_user(db)
        tags = [{"name": "bloating", "severity": 5}]
        ai_text = "Patient experienced moderate bloating after meals."

        symptom = SymptomService.create_symptom_with_tags(
            db, user.id,
            tags=tags,
            ai_generated_text=ai_text
        )

        assert symptom.ai_generated_text == ai_text
        assert symptom.ai_elaborated is True

    def test_create_symptom_with_user_edited_text(self, db: Session):
        """Test creating a symptom with user-edited final notes."""
        user = create_user(db)
        tags = [{"name": "gas", "severity": 4}]
        ai_text = "Patient experienced mild gas."
        user_text = "I had gas after eating beans."

        symptom = SymptomService.create_symptom_with_tags(
            db, user.id,
            tags=tags,
            ai_generated_text=ai_text,
            final_notes=user_text
        )

        assert symptom.final_notes == user_text
        assert symptom.user_edited_elaboration is True

    def test_create_symptom_with_times(self, db: Session):
        """Test creating a symptom with start/end times."""
        user = create_user(db)
        start = datetime.now(timezone.utc) - timedelta(hours=3)
        end = datetime.now(timezone.utc) - timedelta(hours=1)
        tags = [
            {
                "name": "bloating",
                "severity": 6,
                "start_time": start.isoformat(),
                "end_time": end.isoformat()
            }
        ]

        symptom = SymptomService.create_symptom_with_tags(
            db, user.id,
            tags=tags
        )

        assert symptom.start_time is not None
        assert symptom.end_time is not None

    def test_create_symptom_validates_tags(self, db: Session):
        """Test that tags are validated."""
        user = create_user(db)

        # Empty tags should raise error
        with pytest.raises(ValueError, match="At least one tag"):
            SymptomService.create_symptom_with_tags(db, user.id, tags=[])

        # Missing name should raise error
        with pytest.raises(ValueError, match="must have 'name' and 'severity'"):
            SymptomService.create_symptom_with_tags(
                db, user.id,
                tags=[{"severity": 5}]
            )

        # Invalid severity should raise error
        with pytest.raises(ValueError, match="Severity must be"):
            SymptomService.create_symptom_with_tags(
                db, user.id,
                tags=[{"name": "test", "severity": 15}]
            )


class TestSymptomQueries:
    """Tests for symptom query methods."""

    def test_get_symptom_by_id(self, db: Session):
        """Test retrieving a symptom by ID."""
        user = create_user(db)
        symptom = create_symptom(db, user)

        result = SymptomService.get_symptom(db, symptom.id)

        assert result is not None
        assert result.id == symptom.id

    def test_get_nonexistent_symptom(self, db: Session):
        """Test that getting a non-existent symptom returns None."""
        result = SymptomService.get_symptom(db, 99999)

        assert result is None

    def test_get_user_symptoms(self, db: Session):
        """Test getting all symptoms for a user."""
        user = create_user(db)

        # Create symptoms at different times
        for i in range(3):
            create_symptom(
                db, user,
                start_time=datetime.now(timezone.utc) - timedelta(hours=i)
            )

        symptoms = SymptomService.get_user_symptoms(db, user.id)

        assert len(symptoms) == 3
        # Should be ordered by timestamp descending
        for i in range(len(symptoms) - 1):
            assert symptoms[i].timestamp >= symptoms[i + 1].timestamp

    def test_get_user_symptoms_pagination(self, db: Session):
        """Test symptom pagination."""
        user = create_user(db)

        # Create 10 symptoms
        for i in range(10):
            create_symptom(
                db, user,
                start_time=datetime.now(timezone.utc) - timedelta(hours=i)
            )

        # Get first page
        page1 = SymptomService.get_user_symptoms(db, user.id, limit=5, offset=0)
        assert len(page1) == 5

        # Get second page
        page2 = SymptomService.get_user_symptoms(db, user.id, limit=5, offset=5)
        assert len(page2) == 5


class TestSymptomUpdates:
    """Tests for symptom update methods."""

    def test_update_symptom_description(self, db: Session):
        """Test updating symptom description."""
        user = create_user(db)
        symptom = create_symptom(db, user, raw_description="Original")

        result = SymptomService.update_symptom(
            db, symptom.id,
            raw_description="Updated"
        )

        assert result is not None
        assert result.raw_description == "Updated"

    def test_update_symptom_severity(self, db: Session):
        """Test updating symptom severity."""
        user = create_user(db)
        symptom = create_symptom(
            db, user,
            tags=[{"name": "bloating", "severity": 5}]
        )

        result = SymptomService.update_symptom(
            db, symptom.id,
            severity=8
        )

        assert result.severity == 8

    def test_update_nonexistent_symptom(self, db: Session):
        """Test that updating a non-existent symptom returns None."""
        result = SymptomService.update_symptom(
            db, 99999,
            raw_description="Test"
        )

        assert result is None


class TestSymptomDeletion:
    """Tests for symptom deletion."""

    def test_delete_symptom(self, db: Session):
        """Test deleting a symptom."""
        user = create_user(db)
        symptom = create_symptom(db, user)
        symptom_id = symptom.id

        result = SymptomService.delete_symptom(db, symptom_id)

        assert result is True
        assert db.query(Symptom).filter(Symptom.id == symptom_id).first() is None

    def test_delete_nonexistent_symptom(self, db: Session):
        """Test that deleting a non-existent symptom returns False."""
        result = SymptomService.delete_symptom(db, 99999)

        assert result is False


class TestCommonSymptomTypes:
    """Tests for common symptom types."""

    def test_get_common_symptom_types(self):
        """Test getting the list of common symptom types."""
        types = SymptomService.get_common_symptom_types()

        assert len(types) > 0
        assert "Bloating" in types
        assert "Gas" in types
        assert "Nausea" in types


class TestTagSearch:
    """Tests for symptom tag search and autocomplete."""

    def test_search_symptom_tags_matches_user_history(self, db: Session):
        """Test that tag search returns user's historical tags."""
        user = create_user(db)

        # Create symptoms with various tags
        create_symptom(db, user, tags=[{"name": "bloating", "severity": 5}])
        create_symptom(db, user, tags=[{"name": "bloating", "severity": 6}])
        create_symptom(db, user, tags=[{"name": "gas", "severity": 4}])

        results = SymptomService.search_symptom_tags(db, user.id, "blo")

        assert "bloating" in results

    def test_search_symptom_tags_includes_common_types(self, db: Session):
        """Test that tag search includes common symptom types."""
        user = create_user(db)

        results = SymptomService.search_symptom_tags(db, user.id, "nau")

        # Should include common type "Nausea"
        assert any("nausea" in r.lower() for r in results)

    def test_search_symptom_tags_case_insensitive(self, db: Session):
        """Test that tag search is case insensitive."""
        user = create_user(db)
        create_symptom(db, user, tags=[{"name": "Bloating", "severity": 5}])

        results = SymptomService.search_symptom_tags(db, user.id, "BLOAT")

        assert len(results) > 0

    def test_search_symptom_tags_limits_results(self, db: Session):
        """Test that tag search respects limit."""
        user = create_user(db)

        # Create many symptoms
        for i in range(15):
            create_symptom(
                db, user,
                tags=[{"name": f"symptom{i}", "severity": 5}]
            )

        results = SymptomService.search_symptom_tags(
            db, user.id, "symptom", limit=5
        )

        assert len(results) <= 5


class TestMostCommonTags:
    """Tests for most common symptom tags."""

    def test_get_most_common_tags(self, db: Session):
        """Test getting most frequently used tags."""
        user = create_user(db)

        # Create symptoms with varying tag frequencies
        for _ in range(5):
            create_symptom(db, user, tags=[{"name": "bloating", "severity": 6}])
        for _ in range(3):
            create_symptom(db, user, tags=[{"name": "gas", "severity": 4}])
        for _ in range(1):
            create_symptom(db, user, tags=[{"name": "cramping", "severity": 5}])

        results = SymptomService.get_most_common_symptom_tags(db, user.id, limit=3)

        assert len(results) == 3
        # Most common should be first
        assert results[0]["name"] == "bloating"
        assert results[0]["count"] == 5

    def test_get_most_common_tags_calculates_avg_severity(self, db: Session):
        """Test that average severity is calculated."""
        user = create_user(db)

        # Create symptoms with same tag, varying severity
        create_symptom(db, user, tags=[{"name": "bloating", "severity": 4}])
        create_symptom(db, user, tags=[{"name": "bloating", "severity": 8}])

        results = SymptomService.get_most_common_symptom_tags(db, user.id, limit=1)

        # Average of 4 and 8 = 6
        assert results[0]["avg_severity"] == pytest.approx(6.0, abs=0.1)


class TestMostRecentTags:
    """Tests for most recent symptom tags."""

    def test_get_most_recent_tags(self, db: Session):
        """Test getting most recently used tags."""
        user = create_user(db)
        now = datetime.now(timezone.utc)

        # Create symptoms at different times
        create_symptom(
            db, user,
            tags=[{"name": "bloating", "severity": 5}],
            start_time=now - timedelta(hours=1)
        )
        create_symptom(
            db, user,
            tags=[{"name": "gas", "severity": 4}],
            start_time=now - timedelta(hours=2)
        )
        create_symptom(
            db, user,
            tags=[{"name": "cramping", "severity": 6}],
            start_time=now - timedelta(hours=3)
        )

        results = SymptomService.get_most_recent_symptom_tags(db, user.id, limit=3)

        assert len(results) == 3


class TestEpisodeDetection:
    """Tests for episode detection and linking."""

    def test_detect_ongoing_symptom_by_name(self, db: Session):
        """Test detecting an ongoing symptom by name."""
        user = create_user(db)
        now = datetime.now(timezone.utc)

        # Create a recent symptom
        recent = create_symptom(
            db, user,
            tags=[{"name": "bloating", "severity": 6}],
            start_time=now - timedelta(hours=2)
        )

        result = SymptomService.detect_ongoing_symptom_by_name(
            db, user.id,
            symptom_name="bloating",
            lookback_hours=24
        )

        assert result is not None
        assert result.id == recent.id

    def test_detect_ongoing_returns_none_outside_window(self, db: Session):
        """Test that symptoms outside lookback window are not found."""
        user = create_user(db)
        now = datetime.now(timezone.utc)

        # Create an old symptom
        create_symptom(
            db, user,
            tags=[{"name": "bloating", "severity": 6}],
            start_time=now - timedelta(days=5)
        )

        result = SymptomService.detect_ongoing_symptom_by_name(
            db, user.id,
            symptom_name="bloating",
            lookback_hours=72  # 3 days
        )

        assert result is None

    def test_detect_similar_recent_symptoms(self, db: Session):
        """Test detecting similar recent symptoms."""
        user = create_user(db)
        now = datetime.now(timezone.utc)

        # Create a recent symptom with bloating
        recent = create_symptom(
            db, user,
            tags=[{"name": "bloating", "severity": 6}],
            start_time=now - timedelta(hours=12)
        )

        # Check if similar symptoms exist
        result = SymptomService.detect_similar_recent_symptoms(
            db, user.id,
            tags=[{"name": "bloating", "severity": 7}],  # Same name, different severity
            lookback_hours=48
        )

        assert result is not None
        assert result.id == recent.id

    def test_detect_similar_returns_none_for_different_symptoms(self, db: Session):
        """Test that different symptoms are not detected as similar."""
        user = create_user(db)
        now = datetime.now(timezone.utc)

        # Create a recent symptom with bloating
        create_symptom(
            db, user,
            tags=[{"name": "bloating", "severity": 6}],
            start_time=now - timedelta(hours=12)
        )

        # Check for completely different symptom
        result = SymptomService.detect_similar_recent_symptoms(
            db, user.id,
            tags=[{"name": "headache", "severity": 5}],
            lookback_hours=48
        )

        assert result is None

    def test_link_episode(self, db: Session):
        """Test linking a symptom to a previous episode."""
        user = create_user(db)

        # Create initial symptom
        initial = create_symptom(db, user)

        # Create follow-up symptom
        followup = create_symptom(db, user)

        result = SymptomService.link_episode(db, followup.id, initial.id)

        assert result is True

        # Verify link
        db.refresh(followup)
        assert followup.episode_id == initial.id

    def test_link_episode_nonexistent_symptom(self, db: Session):
        """Test that linking a non-existent symptom returns False."""
        user = create_user(db)
        initial = create_symptom(db, user)

        result = SymptomService.link_episode(db, 99999, initial.id)

        assert result is False
