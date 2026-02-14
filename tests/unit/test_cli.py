"""
Unit tests for CLI commands.

Tests the command-line interface for admin operations.
"""
import pytest
import sys
from io import StringIO
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session

from app.cli import create_admin, main
from app.models.user import User


# =============================================================================
# create_admin Tests
# =============================================================================

class TestCreateAdmin:
    """Tests for the create_admin function."""

    def test_create_admin_success(self, db: Session):
        """Test successful admin creation."""
        with patch('app.cli.SessionLocal', return_value=db), \
             patch('builtins.print') as mock_print:

            create_admin("admin@test.com", "securepassword123")

            # Verify user was created
            user = db.query(User).filter(User.email == "admin@test.com").first()
            assert user is not None
            assert user.is_admin is True
            assert user.email == "admin@test.com"

            # Verify success message
            mock_print.assert_called_with("Admin user created successfully: admin@test.com")

    def test_create_admin_email_normalized(self, db: Session):
        """Test that email is normalized to lowercase."""
        with patch('app.cli.SessionLocal', return_value=db), \
             patch('builtins.print'):

            create_admin("Admin@Test.COM", "password123")

            user = db.query(User).filter(User.email == "admin@test.com").first()
            assert user is not None

    def test_create_admin_duplicate_email(self, db: Session, test_user):
        """Test error when email already exists."""
        with patch('app.cli.SessionLocal', return_value=db), \
             patch('builtins.print') as mock_print, \
             pytest.raises(SystemExit) as exc_info:

            create_admin(test_user.email, "newpassword123")

        assert exc_info.value.code == 1
        mock_print.assert_called()
        assert "already exists" in str(mock_print.call_args)

    def test_create_admin_password_too_short(self, db: Session):
        """Test error when password is too short."""
        with patch('app.cli.SessionLocal', return_value=db), \
             patch('builtins.print') as mock_print, \
             pytest.raises(SystemExit) as exc_info:

            create_admin("admin@test.com", "short")

        assert exc_info.value.code == 1
        mock_print.assert_called()
        assert "at least 8 characters" in str(mock_print.call_args)

    def test_create_admin_prompts_for_password(self, db: Session):
        """Test that password is prompted if not provided."""
        with patch('app.cli.SessionLocal', return_value=db), \
             patch('getpass.getpass', side_effect=["password123", "password123"]), \
             patch('builtins.print'):

            create_admin("prompttest@test.com")

            user = db.query(User).filter(User.email == "prompttest@test.com").first()
            assert user is not None

    def test_create_admin_password_mismatch(self, db: Session):
        """Test error when password confirmation doesn't match."""
        with patch('app.cli.SessionLocal', return_value=db), \
             patch('getpass.getpass', side_effect=["password123", "different456"]), \
             patch('builtins.print') as mock_print, \
             pytest.raises(SystemExit) as exc_info:

            create_admin("mismatch@test.com")

        assert exc_info.value.code == 1
        mock_print.assert_called()
        assert "do not match" in str(mock_print.call_args)

    def test_create_admin_password_hash_is_valid(self, db: Session):
        """Test that password is properly hashed."""
        import bcrypt

        with patch('app.cli.SessionLocal', return_value=db), \
             patch('builtins.print'):

            create_admin("hashtest@test.com", "password123")

            user = db.query(User).filter(User.email == "hashtest@test.com").first()
            assert user is not None
            # Verify password can be verified
            assert bcrypt.checkpw(
                "password123".encode('utf-8'),
                user.password_hash.encode('utf-8')
            )


# =============================================================================
# main() Tests
# =============================================================================

class TestMain:
    """Tests for the main CLI entry point."""

    def test_main_create_admin(self, db: Session):
        """Test main with create-admin command."""
        with patch('app.cli.SessionLocal', return_value=db), \
             patch('sys.argv', ['bloaty', 'create-admin', '--email', 'cli@test.com', '--password', 'password123']), \
             patch('builtins.print'):

            main()

            user = db.query(User).filter(User.email == "cli@test.com").first()
            assert user is not None
            assert user.is_admin is True

    def test_main_no_command_shows_help(self):
        """Test that no command shows help and exits."""
        with patch('sys.argv', ['bloaty']), \
             pytest.raises(SystemExit) as exc_info:

            main()

        assert exc_info.value.code == 1

    def test_main_unknown_command(self):
        """Test that unknown command shows error."""
        with patch('sys.argv', ['bloaty', 'unknown-command']), \
             pytest.raises(SystemExit) as exc_info:

            main()

        # argparse returns exit code 2 for invalid arguments
        assert exc_info.value.code == 2

    def test_main_create_admin_missing_email(self):
        """Test that missing email argument shows error."""
        with patch('sys.argv', ['bloaty', 'create-admin']), \
             pytest.raises(SystemExit):

            main()

    def test_main_help(self):
        """Test --help option."""
        with patch('sys.argv', ['bloaty', '--help']), \
             pytest.raises(SystemExit) as exc_info:

            main()

        # Help exits with 0
        assert exc_info.value.code == 0

    def test_main_create_admin_help(self):
        """Test create-admin --help."""
        with patch('sys.argv', ['bloaty', 'create-admin', '--help']), \
             pytest.raises(SystemExit) as exc_info:

            main()

        assert exc_info.value.code == 0


# =============================================================================
# Database Session Cleanup Tests
# =============================================================================

class TestDatabaseCleanup:
    """Tests for proper database session cleanup."""

    def test_session_closed_on_success(self, db: Session):
        """Test that session is closed after successful operation."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        with patch('app.cli.SessionLocal', return_value=mock_session), \
             patch('builtins.print'):

            create_admin("cleanup@test.com", "password123")

            mock_session.close.assert_called_once()

    def test_session_closed_on_error(self, db: Session, test_user):
        """Test that session is closed even when error occurs."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = test_user

        with patch('app.cli.SessionLocal', return_value=mock_session), \
             patch('builtins.print'), \
             pytest.raises(SystemExit):

            create_admin(test_user.email, "password123")

            mock_session.close.assert_called_once()
