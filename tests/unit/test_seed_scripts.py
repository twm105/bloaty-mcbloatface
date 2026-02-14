"""
Unit tests for seed scripts.

Tests the database seeding functionality for:
- Ingredient categories
- MVP user
"""
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session

from app.models import User, IngredientCategory
from app.models.user_settings import UserSettings
from tests.factories import create_user


class TestSeedCategories:
    """Tests for seed_categories function."""

    def test_seed_categories_creates_root_categories(self, db: Session):
        """Test that seed_categories creates root categories."""
        from app.seed_categories import seed_categories

        # Ensure no categories exist
        db.query(IngredientCategory).delete()
        db.commit()

        # Run with mocked SessionLocal returning our test db
        with patch('app.seed_categories.SessionLocal', return_value=db):
            seed_categories()

        # Check categories were created
        categories = db.query(IngredientCategory).all()
        assert len(categories) == 12

        # Check some specific categories exist
        names = [c.name for c in categories]
        assert "Dairy" in names
        assert "Grains" in names
        assert "Proteins" in names
        assert "FODMAPs" in names

    def test_seed_categories_skips_if_exists(self, db: Session):
        """Test that seed_categories skips if categories already exist."""
        from app.seed_categories import seed_categories

        # Create one category first
        category = IngredientCategory(
            name="Test",
            normalized_name="test",
            level=0
        )
        db.add(category)
        db.commit()

        initial_count = db.query(IngredientCategory).count()

        with patch('app.seed_categories.SessionLocal', return_value=db):
            seed_categories()

        # Should not have added more categories
        assert db.query(IngredientCategory).count() == initial_count

    def test_seed_categories_rollback_on_error(self, db: Session):
        """Test that seed_categories rolls back on error."""
        from app.seed_categories import seed_categories

        # Ensure no categories exist
        db.query(IngredientCategory).delete()
        db.commit()

        # Mock commit to raise an error
        mock_db = MagicMock()
        mock_db.query.return_value.count.return_value = 0
        mock_db.commit.side_effect = Exception("Database error")

        with patch('app.seed_categories.SessionLocal', return_value=mock_db):
            with pytest.raises(Exception, match="Database error"):
                seed_categories()

        mock_db.rollback.assert_called_once()


class TestSeedUser:
    """Tests for seed_user function."""

    def test_seed_user_creates_mvp_user(self, db: Session):
        """Test that seed_user creates the MVP user."""
        from app.seed_user import seed_user, MVP_USER_ID

        # Ensure user doesn't exist
        db.query(User).filter(User.id == MVP_USER_ID).delete()
        db.query(UserSettings).filter(UserSettings.user_id == MVP_USER_ID).delete()
        db.commit()

        with patch('app.seed_user.SessionLocal', return_value=db):
            seed_user()

        # Check user was created
        user = db.query(User).filter(User.id == MVP_USER_ID).first()
        assert user is not None
        assert user.id == MVP_USER_ID

        # Check settings were created
        settings = db.query(UserSettings).filter(UserSettings.user_id == MVP_USER_ID).first()
        assert settings is not None
        assert settings.disclaimer_acknowledged is False

    def test_seed_user_skips_if_exists(self, db: Session):
        """Test that seed_user skips if user already exists."""
        from app.seed_user import seed_user, MVP_USER_ID

        # Create the user first
        user = User(id=MVP_USER_ID, email=None)
        db.add(user)
        db.commit()

        # Running again should not fail
        with patch('app.seed_user.SessionLocal', return_value=db):
            seed_user()

        # Still just one user
        count = db.query(User).filter(User.id == MVP_USER_ID).count()
        assert count == 1

    def test_seed_user_rollback_on_error(self, db: Session):
        """Test that seed_user rolls back on error."""
        from app.seed_user import seed_user

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.commit.side_effect = Exception("Database error")

        with patch('app.seed_user.SessionLocal', return_value=mock_db):
            with pytest.raises(Exception, match="Database error"):
                seed_user()

        mock_db.rollback.assert_called_once()

    def test_mvp_user_id_is_correct(self):
        """Test that MVP_USER_ID is the expected value."""
        from app.seed_user import MVP_USER_ID
        import uuid

        assert MVP_USER_ID == uuid.UUID("00000000-0000-0000-0000-000000000000")
