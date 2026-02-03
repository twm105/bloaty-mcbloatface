# Test Organization

## Directory Structure

```
tests/
├── unit/              # Unit tests for individual functions/classes
├── integration/       # Integration tests for API endpoints and services
├── fixtures/          # Test data, fixtures, and data generation scripts
├── scripts/           # Helper scripts for testing (bash, etc.)
├── conftest.py        # Pytest configuration and shared fixtures
└── __init__.py
```

## Test Types

### Unit Tests (`unit/`)
Fast, isolated tests for individual functions, classes, or modules:
- **Models**: `unit/models/test_meal.py`, `unit/models/test_ingredient.py`
- **Services**: `unit/services/test_confidence_scoring.py`, `unit/services/test_ai_service.py`
- **Utilities**: `unit/utils/test_validators.py`

**Characteristics**:
- Mock external dependencies (database, API calls)
- Fast execution (<100ms per test)
- Focus on single units of code

### Integration Tests (`integration/`)
Tests that verify components working together:
- **API endpoints**: `integration/test_diagnosis_api.py`, `integration/test_meals_api.py`
- **Database operations**: `integration/test_diagnosis_service.py`
- **End-to-end flows**: `integration/test_meal_upload_flow.py`

**Characteristics**:
- Use test database
- May involve multiple services
- Slower but more comprehensive

### Fixtures (`fixtures/`)
Test data and data generation:
- `create_test_data.py` - Script to generate realistic test data
- `create_test_data.sql` - SQL for test data creation
- JSON fixtures for API request/response examples

### Scripts (`scripts/`)
Helper scripts for testing:
- `run_diagnosis_test.sh` - Diagnosis feature test script
- Other bash/python scripts for test automation

## Running Tests

```bash
# All tests
pytest

# Unit tests only (fast)
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# Specific test file
pytest tests/integration/test_diagnosis_api.py

# With coverage
pytest --cov=app tests/

# Verbose output
pytest -v
```

## Writing New Tests

### Unit Test Example
```python
# tests/unit/services/test_confidence_scoring.py
import pytest
from app.services.diagnosis_service import DiagnosisService

def test_calculate_confidence_high():
    """Test confidence calculation for strong correlation"""
    service = DiagnosisService(db=None)
    score, level = service.calculate_confidence(
        times_eaten=10,
        symptom_occurrences=9,
        immediate_count=8,
        delayed_count=1,
        cumulative_count=0,
        avg_severity=7.0
    )
    assert level == "high"
    assert score > 0.8
```

### Integration Test Example
```python
# tests/integration/test_diagnosis_api.py
import pytest
from fastapi.testclient import TestClient

def test_run_diagnosis(client: TestClient, test_db):
    """Test diagnosis API endpoint"""
    response = client.post("/diagnosis/analyze", json={
        "web_search_enabled": False,
        "min_meals": 5
    })
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    assert data["sufficient_data"] is True
```

## Best Practices

1. **One assertion concept per test**: Focus on testing one thing
2. **Descriptive test names**: `test_confidence_high_with_immediate_symptoms` not `test1`
3. **Arrange-Act-Assert**: Structure tests clearly
4. **Use fixtures**: Share setup code via conftest.py
5. **Mock external APIs**: Don't call real Claude API in tests
6. **Clean up**: Use teardown fixtures to clean test data

## Future Test Coverage Goals

- [ ] Unit tests for all service methods
- [ ] Integration tests for all API endpoints
- [ ] Model validation tests
- [ ] Edge case and error handling tests
- [ ] Performance/load tests
- [ ] Frontend E2E tests (Playwright)
