# Testing Strategy

This document outlines the testing philosophy, patterns, and practices for Bloaty McBloatface. It serves as a conceptual guide—implementation details will evolve as we build out the test suite.

## Philosophy

### Lock-in Then Test

We follow a **lock-in then test** approach rather than strict TDD:

1. **Iterate rapidly** on features without test overhead during exploration
2. **Lock in behavior** once a feature stabilizes
3. **Write tests** before merging to main to prevent regressions
4. **Enforce coverage** on changed files via pre-commit hooks

This balances development velocity with long-term maintainability. Tests become documentation of intended behavior once we're confident in the implementation.

### Coverage Requirements

- **Before merge to main:** All changed files must have test coverage for new/modified code paths
- **Pre-commit hook:** Blocks commits that reduce coverage on touched files
- **Exemptions:** Templates, migrations, and config files are excluded from coverage requirements

## Quick Start

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=app --cov-report=term-missing

# Run specific test category
pytest tests/unit/
pytest tests/integration/
pytest tests/security/ -m security

# Use cached API responses (default, zero API cost)
pytest --use-cached-responses

# Refresh API response cache (incurs API costs)
pytest --refresh-api-cache

# Run tests for changed files only
pytest --changed-only  # requires pytest-changed plugin or custom impl
```

## Test Categories

### Unit Tests (`tests/unit/`)

Test individual functions and classes in isolation.

**Scope:**
- Model validation and methods
- Service business logic (with mocked dependencies)
- Utility functions
- Data transformations

**Patterns:**
- Mock external dependencies (database, APIs)
- Test edge cases and error handling
- Keep tests fast (<100ms each)

```python
# Example: Testing ingredient normalization
def test_normalize_ingredient_strips_whitespace():
    assert normalize_ingredient("  chicken breast  ") == "chicken breast"

def test_normalize_ingredient_lowercases():
    assert normalize_ingredient("CHICKEN BREAST") == "chicken breast"
```

### Integration Tests (`tests/integration/`)

Test component interactions and API endpoints.

**Scope:**
- FastAPI endpoint responses
- Database operations (CRUD, queries)
- AI service integration (with cached responses)
- Template rendering

**Patterns:**
- Use TestClient for API tests
- Real database with transaction rollback
- Cached API responses for AI tests

```python
# Example: Testing meal creation endpoint
def test_create_meal_returns_201(client, db, auth_headers):
    response = client.post(
        "/api/meals",
        json={"description": "Grilled chicken salad"},
        headers=auth_headers
    )
    assert response.status_code == 201
    assert "id" in response.json()
```

### Security Tests (`tests/security/`)

Separate track for security-focused testing. See [Security Testing](#security-testing) section below.

## Database Isolation

### Transaction Rollback Pattern

Each test runs in a database transaction that's rolled back after completion. This provides:
- **Isolation:** Tests can't affect each other
- **Speed:** No cleanup queries needed
- **Simplicity:** Just yield and rollback

```python
# conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database import Base

@pytest.fixture(scope="session")
def test_engine():
    """Create test database engine once per session."""
    engine = create_engine("postgresql://test:test@localhost/bloaty_test")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture
def db(test_engine):
    """Provide a transactional database session that rolls back after each test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()
```

### Factory Functions

Use factory functions to create test data consistently:

```python
# tests/factories.py
def create_user(db, **overrides):
    defaults = {
        "email": "test@example.com",
        "username": "testuser",
        "password_hash": "hashed_password"
    }
    user = User(**{**defaults, **overrides})
    db.add(user)
    db.flush()  # Get ID without committing
    return user

def create_meal(db, user, **overrides):
    defaults = {
        "user_id": user.id,
        "description": "Test meal",
        "logged_at": datetime.utcnow()
    }
    meal = Meal(**{**defaults, **overrides})
    db.add(meal)
    db.flush()
    return meal
```

## API Response Caching

### The Problem

AI analysis endpoints call Claude API, which:
- Costs money per request
- Adds latency to test runs
- May vary slightly between calls (non-deterministic)

### The Solution: Cache + Replay

Cache API responses to JSON files, keyed by request hash. Tests use cached responses by default; refresh explicitly when needed.

```python
# tests/fixtures/api_cache.py
import hashlib
import json
from pathlib import Path
from functools import wraps

CACHE_DIR = Path(__file__).parent / "api_responses"
CACHE_DIR.mkdir(exist_ok=True)

def cached_api_response(func):
    """Decorator that caches API responses for test replay."""
    @wraps(func)
    def wrapper(*args, use_cache=True, **kwargs):
        # Generate cache key from function name and arguments
        cache_key = hashlib.sha256(
            f"{func.__name__}:{args}:{sorted(kwargs.items())}".encode()
        ).hexdigest()[:16]

        cache_file = CACHE_DIR / f"{func.__name__}_{cache_key}.json"

        if use_cache and cache_file.exists():
            return json.loads(cache_file.read_text())

        # Make actual API call
        result = func(*args, **kwargs)

        # Cache the response
        cache_file.write_text(json.dumps(result, indent=2))
        return result

    return wrapper
```

### pytest Plugin Configuration

```python
# conftest.py
def pytest_addoption(parser):
    parser.addoption(
        "--use-cached-responses",
        action="store_true",
        default=True,
        help="Use cached API responses (default)"
    )
    parser.addoption(
        "--refresh-api-cache",
        action="store_true",
        default=False,
        help="Refresh API response cache (incurs costs)"
    )

@pytest.fixture
def use_api_cache(request):
    """Returns False if --refresh-api-cache is set."""
    return not request.config.getoption("--refresh-api-cache")
```

### Cache File Structure

```
tests/fixtures/api_responses/
├── analyze_meal_image_a1b2c3d4.json
├── analyze_meal_image_e5f6g7h8.json
├── elaborate_symptom_i9j0k1l2.json
└── generate_diagnosis_m3n4o5p6.json
```

Each file contains:
```json
{
  "request": {
    "model": "claude-3-haiku-20240307",
    "prompt_hash": "abc123...",
    "timestamp": "2024-01-15T10:30:00Z"
  },
  "response": {
    "ingredients": ["chicken", "rice", "broccoli"],
    "confidence": 0.92
  }
}
```

## Image Test Data

### Curated Fixture Images

Maintain a small set (10-15) of diverse meal images in `tests/fixtures/images/`:

| Image | Purpose | Expected Analysis |
|-------|---------|-------------------|
| `simple_salad.jpg` | Basic case | lettuce, tomato, cucumber |
| `complex_curry.jpg` | Many ingredients | rice, chicken, curry sauce, onion, garlic |
| `poor_lighting.jpg` | Edge case: dark image | Should still detect main items |
| `multiple_dishes.jpg` | Edge case: plate variety | Should identify all dishes |
| `non_food.jpg` | Negative case | Should return empty or error |
| `blurry_meal.jpg` | Edge case: low quality | Graceful degradation |
| `raw_ingredients.jpg` | State detection | Raw vegetables, uncooked meat |
| `cooked_meal.jpg` | State detection | Cooked/processed items |

### Manifest File

Document expected results alongside images:

```yaml
# tests/fixtures/images/manifest.yaml
simple_salad.jpg:
  expected_ingredients:
    - name: lettuce
      state: raw
    - name: tomato
      state: raw
    - name: cucumber
      state: raw
  notes: "Clear lighting, single dish, common ingredients"

poor_lighting.jpg:
  expected_ingredients:
    - name: pasta
      state: cooked
  notes: "May have lower confidence due to lighting"
  acceptable_confidence_threshold: 0.6
```

### Synthetic Image Generation

For edge cases that are hard to photograph, generate synthetic test images:

```python
from PIL import Image, ImageDraw

def create_solid_color_image(color, size=(640, 480)):
    """Create a solid color image for testing non-food detection."""
    return Image.new("RGB", size, color)

def create_gradient_image():
    """Create a gradient image for testing edge detection."""
    img = Image.new("RGB", (640, 480))
    # ... gradient generation logic
    return img
```

## Worktree Considerations

When using git worktrees, each worktree has the same `.git` but separate working directories. This affects test isolation.

### Database Isolation

Each worktree needs its own test database to prevent conflicts:

```python
# conftest.py
import os
import subprocess

def get_worktree_suffix():
    """Get a unique suffix based on the current worktree."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True
    )
    # Hash the worktree path to create a short unique suffix
    path = result.stdout.strip()
    return hashlib.sha256(path.encode()).hexdigest()[:8]

TEST_DB_NAME = f"bloaty_test_{get_worktree_suffix()}"
```

Alternatively, use SQLite for tests (simpler, file-based isolation):

```python
# Each worktree gets its own test.db in its directory
TEST_DB_URL = f"sqlite:///{Path(__file__).parent}/test.db"
```

### Cache Path Handling

API response caches in `tests/fixtures/api_responses/` are shared across worktrees (same git repo). Options:

1. **Accept sharing:** Cache files are deterministic, sharing is fine
2. **Worktree-specific caches:** Use `.gitignore` for cached responses
3. **Separate cache dirs:** `tests/fixtures/api_responses_{worktree_suffix}/`

Recommended: Accept sharing with `.gitignore` for the cache directory.

```gitignore
# .gitignore
tests/fixtures/api_responses/
```

## Merge & Integration Workflow

### Worktrees as Distributed Agents

When using git worktrees with multiple Claude Code agents, each worktree is like an independent developer. Merges to main are equivalent to PRs—the integration point where work comes together.

**Recommended Workflow:**
1. Agent completes work in feature worktree
2. Agent switches to main worktree
3. Agent merges feature → main
4. **Agent runs tests on merged result** (simulates PR CI check)
5. If green: push to remote
6. If red: fix locally before pushing

This is **post-merge, pre-push testing**—it simulates PR CI checks (tests the merged result), keeps main green both locally and remotely, and allows agents to work fast while validating before sharing.

### Test Commands for Merge Validation

```bash
# After merging, before pushing - run from main worktree:

# Quick regression check (~15s) - catches obvious breaks
docker compose exec web pytest tests/unit/ -x --tb=short

# Full validation (~75s) - ensures nothing broke
docker compose exec web pytest tests/ --cov=app --cov-fail-under=80

# Coverage report - check new code is tested
docker compose exec web pytest tests/ --cov=app --cov-report=term-missing
```

### What Each Check Validates

| Check | Purpose | When to Use |
|-------|---------|-------------|
| **Unit tests only** | Fast regression catch | Every merge |
| **Full suite** | Complete regression + coverage | Before pushing to remote |
| **Coverage report** | Ensure new code tested | When adding features |

### Remote CI as Safety Net

Even with local testing, CI runs on push as a safety net:
- Catches environment-specific issues
- Aggregates coverage reports
- Provides audit trail

### Handling Conflicts Between Agents

When multiple agents merge to main:
1. First agent's merge + push succeeds normally
2. Second agent's push fails (remote has new commits)
3. Second agent pulls, re-runs tests on re-merged result
4. If green: push; if red: fix conflicts

This mirrors the standard PR workflow where base branch updates require re-testing.

## Security Testing

Security tests live in a separate directory and run independently from the main test suite.

### Directory Structure

```
tests/security/
├── conftest.py
├── test_auth.py
├── test_input_validation.py
├── test_sql_injection.py
├── test_xss.py
└── test_csrf.py
```

### Running Security Tests

```bash
# Run security tests only
pytest tests/security/ -m security

# Include in CI but allow failures (advisory)
pytest tests/security/ -m security --ignore-failures
```

### OWASP Top 10 Checklist

Reference checklist for security test coverage:

| Category | Status | Test File |
|----------|--------|-----------|
| A01: Broken Access Control | TODO | `test_auth.py` |
| A02: Cryptographic Failures | TODO | `test_crypto.py` |
| A03: Injection (SQL, Command) | TODO | `test_sql_injection.py` |
| A04: Insecure Design | TODO | — |
| A05: Security Misconfiguration | TODO | `test_config.py` |
| A06: Vulnerable Components | TODO | dependency audit |
| A07: Auth Failures | TODO | `test_auth.py` |
| A08: Software/Data Integrity | TODO | — |
| A09: Logging Failures | TODO | `test_logging.py` |
| A10: SSRF | TODO | `test_ssrf.py` |

### htmx-Specific Security

htmx endpoints need special attention:

```python
# test_xss.py
def test_htmx_response_escapes_user_input(client, db, auth_headers):
    """Ensure htmx partials don't render unescaped user content."""
    # Create meal with XSS attempt in description
    malicious_input = "<script>alert('xss')</script>"
    response = client.post(
        "/api/meals",
        json={"description": malicious_input},
        headers=auth_headers
    )

    # Fetch the rendered partial
    meal_id = response.json()["id"]
    partial = client.get(f"/partials/meals/{meal_id}", headers=auth_headers)

    # Script tag should be escaped, not rendered
    assert "<script>" not in partial.text
    assert "&lt;script&gt;" in partial.text or malicious_input not in partial.text
```

## CI/CD Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/test.yml
name: Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: bloaty_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          pip install -e ".[dev]"

      - name: Run tests with coverage
        env:
          DATABASE_URL: postgresql://test:test@localhost/bloaty_test
        run: |
          pytest --cov=app --cov-report=xml --cov-fail-under=80

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: coverage.xml

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run security tests
        run: pytest tests/security/ -m security
        continue-on-error: true  # Advisory, don't block PR
```

### Pre-commit Hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: pytest-changed
        name: pytest changed files
        entry: pytest --changed-only --cov-fail-under=80
        language: system
        pass_filenames: false
        stages: [commit]
```

### Coverage Thresholds

**Current state:** 95% coverage with 643 tests.

| Category | Minimum Coverage | Current |
|----------|------------------|---------|
| Overall | 80% | 95% |
| New code in PR | 90% | — |
| Models | 95% | ✓ |
| Services | 85% | ✓ |
| API routes | 75% | ✓ |

## Future: `/test` Skill

If the testing workflow becomes repetitive, consider implementing a `/test` skill:

```bash
# Potential usage
/test                    # Run tests for changed files
/test --all              # Run full test suite
/test --coverage         # Run with coverage report
/test --security         # Run security tests
/test --fix              # Auto-generate test stubs for uncovered code
```

**Implementation notes:**
- Parse git diff to identify changed files
- Map changed files to corresponding test files
- Run pytest with appropriate filters
- Display failed tests with context
- Optionally generate test stubs for new functions

**Decision:** Start with documented pytest commands. Add `/test` skill if workflow proves repetitive after building out initial test coverage.

---

## Appendix: Test Utilities Checklist

Utilities to implement when building test infrastructure:

- [x] `conftest.py` with database fixtures (transaction rollback)
- [x] `factories.py` for creating test data
- [x] API mocking via `tests/fixtures/mocks.py` (mocks Claude API responses)
- [x] GitHub Actions workflow for CI/CD (`.github/workflows/test.yml`)
- [x] Security test directory structure (`tests/security/`)
- [ ] Curated image fixtures with manifest
- [ ] Pre-commit hook for coverage enforcement
