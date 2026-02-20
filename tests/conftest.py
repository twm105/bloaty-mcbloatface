"""
Test configuration and fixtures for Bloaty McBloatface.

Implements the transaction rollback pattern from TESTING.md:
- Session-scoped PostgreSQL engine
- Function-scoped transactional session with automatic rollback
- TestClient with database dependency override
- Authenticated client fixtures
- API response caching options
"""

import os
import hashlib
import subprocess
from typing import Generator
from datetime import datetime, timedelta, timezone
import secrets

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import User, Session as UserSession, Invite


# =============================================================================
# pytest Configuration
# =============================================================================


def pytest_addoption(parser):
    """Add custom pytest command line options."""
    parser.addoption(
        "--use-cached-responses",
        action="store_true",
        default=True,
        help="Use cached API responses (default)",
    )
    parser.addoption(
        "--refresh-api-cache",
        action="store_true",
        default=False,
        help="Refresh API response cache (incurs costs)",
    )


@pytest.fixture
def use_api_cache(request) -> bool:
    """Returns False if --refresh-api-cache is set."""
    return not request.config.getoption("--refresh-api-cache")


@pytest.fixture(autouse=True, scope="session")
def configure_api_cache(request):
    """
    Configure API response caching for the test session.

    By default, caching is enabled (uses cached responses).
    Use --refresh-api-cache to disable caching and make real API calls.
    """
    from tests.fixtures.api_cache import set_cache_enabled

    use_cache = not request.config.getoption("--refresh-api-cache")
    set_cache_enabled(use_cache)

    yield

    # Reset to default (disabled) after tests
    set_cache_enabled(False)


# =============================================================================
# Database Fixtures
# =============================================================================


def get_worktree_suffix() -> str:
    """Get a unique suffix based on the current worktree for test isolation."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
        )
        path = result.stdout.strip()
        return hashlib.sha256(path.encode()).hexdigest()[:8]
    except Exception:
        return "default"


def get_test_database_url() -> str:
    """
    Get the test database URL.

    Priority:
    1. TEST_DATABASE_URL environment variable
    2. Use DATABASE_URL directly (transaction rollback ensures isolation)
    3. Default test database for local development

    Note: We use the main database with transaction rollback pattern.
    Each test runs in a transaction that is rolled back after the test,
    so no test data persists and tests are fully isolated.
    """
    if os.environ.get("TEST_DATABASE_URL"):
        return os.environ["TEST_DATABASE_URL"]

    # Use main DATABASE_URL directly - transaction rollback ensures isolation
    main_url = os.environ.get("DATABASE_URL", "")
    if main_url and "postgresql" in main_url:
        return main_url

    # Default for local development (outside Docker)
    return "postgresql://postgres:postgres@localhost:5432/bloaty"


@pytest.fixture(scope="session")
def test_engine():
    """
    Create test database engine once per session.

    The engine is created at session scope for efficiency.
    Tables are created at the start and dropped at the end.
    """
    database_url = get_test_database_url()

    # For CI environments, use the DATABASE_URL directly
    if os.environ.get("CI"):
        database_url = os.environ.get("DATABASE_URL", database_url)

    engine = create_engine(database_url)

    # Create all tables
    Base.metadata.create_all(engine)

    yield engine

    # Cleanup: only drop tables in CI (ephemeral database)
    # In local dev, we share the database and use transaction rollback for isolation
    if os.environ.get("CI"):
        Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(test_engine) -> Generator[Session, None, None]:
    """
    Provide a transactional database session that rolls back after each test.

    This pattern ensures:
    - Complete test isolation (tests can't affect each other)
    - No cleanup queries needed
    - Fast execution (just rollback, no actual deletion)
    """
    # Start a connection and transaction
    connection = test_engine.connect()
    transaction = connection.begin()

    # Create a session bound to this connection
    TestingSessionLocal = sessionmaker(bind=connection)
    session = TestingSessionLocal()

    # Handle nested transactions (for savepoints within tests)
    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(session, transaction):
        if transaction.nested and not transaction._parent.nested:
            session.begin_nested()

    yield session

    # Cleanup: rollback and close
    session.close()
    transaction.rollback()
    connection.close()


# =============================================================================
# TestClient Fixtures
# =============================================================================


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    """
    TestClient with database dependency override.

    The database session is injected into the app's get_db dependency.
    """

    def override_get_db():
        try:
            yield db
        finally:
            pass  # Don't close - managed by db fixture

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        # Set default Referer so CSRF Origin middleware allows requests
        test_client.headers["referer"] = "http://testserver/"
        yield test_client

    app.dependency_overrides.clear()


# =============================================================================
# Authentication Fixtures
# =============================================================================


@pytest.fixture
def test_user(db: Session) -> User:
    """Create a test user."""
    import bcrypt

    password_hash = bcrypt.hashpw(
        "testpassword123".encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    user = User(
        email="testuser@example.com", password_hash=password_hash, is_admin=False
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def admin_user(db: Session) -> User:
    """Create an admin test user."""
    import bcrypt

    password_hash = bcrypt.hashpw(
        "adminpassword123".encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    user = User(email="admin@example.com", password_hash=password_hash, is_admin=True)
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def test_session(db: Session, test_user: User) -> UserSession:
    """Create a test session for the test user."""
    token = secrets.token_urlsafe(32)
    session = UserSession(
        user_id=test_user.id,
        token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        user_agent="pytest-test-client",
        ip_address="127.0.0.1",
    )
    db.add(session)
    db.flush()
    return session


@pytest.fixture
def admin_session(db: Session, admin_user: User) -> UserSession:
    """Create a test session for the admin user."""
    token = secrets.token_urlsafe(32)
    session = UserSession(
        user_id=admin_user.id,
        token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        user_agent="pytest-test-client",
        ip_address="127.0.0.1",
    )
    db.add(session)
    db.flush()
    return session


@pytest.fixture
def auth_client(
    db: Session, test_session: UserSession
) -> Generator[TestClient, None, None]:
    """
    Authenticated TestClient for regular user.

    Creates a separate TestClient instance to avoid cookie conflicts.
    """
    from app.config import settings

    def override_get_db():
        try:
            yield db
        finally:
            pass  # Don't close - managed by db fixture

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        test_client.cookies.set(settings.session_cookie_name, test_session.token)
        # Set default Referer so CSRF Origin middleware allows requests
        test_client.headers["referer"] = "http://testserver/"
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def admin_client(
    db: Session, admin_session: UserSession
) -> Generator[TestClient, None, None]:
    """
    Authenticated TestClient for admin user.

    Creates a separate TestClient instance to avoid cookie conflicts.
    """
    from app.config import settings

    def override_get_db():
        try:
            yield db
        finally:
            pass  # Don't close - managed by db fixture

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        test_client.cookies.set(settings.session_cookie_name, admin_session.token)
        # Set default Referer so CSRF Origin middleware allows requests
        test_client.headers["referer"] = "http://testserver/"
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(test_session: UserSession) -> dict:
    """Headers dict with session cookie for use with requests."""
    from app.config import settings

    return {"Cookie": f"{settings.session_cookie_name}={test_session.token}"}


# =============================================================================
# Test Data Fixtures
# =============================================================================


@pytest.fixture
def valid_invite(db: Session, admin_user: User) -> Invite:
    """Create a valid invite token."""
    token = secrets.token_urlsafe(32)
    invite = Invite(
        token=token,
        created_by=admin_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invite)
    db.flush()
    return invite


# =============================================================================
# Mock Fixtures
# =============================================================================


@pytest.fixture
def mock_claude_service(monkeypatch):
    """
    Mock Claude service for testing AI functionality.

    Returns a mock service that can be configured per test.
    """
    from tests.fixtures.mocks import MockClaudeService

    mock_service = MockClaudeService()

    # Patch the ClaudeService import in services
    monkeypatch.setattr("app.services.ai_service.ClaudeService", lambda: mock_service)

    return mock_service


# =============================================================================
# pytest markers
# =============================================================================


def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers",
        "security: marks tests as security tests (deselect with '-m not security')",
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m not slow')"
    )
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line(
        "markers",
        "ai_integration: marks tests that use real AI API (use --refresh-api-cache to refresh)",
    )
