# Test Organization Summary

## Project Root Cleanup - Complete ✅

All test files have been moved from project root to organized subdirectories.

## New Structure

```
tests/
├── unit/                          # Unit tests (fast, isolated)
│   └── __init__.py
│
├── integration/                   # Integration tests (API, services, DB)
│   ├── __init__.py
│   └── test_diagnosis.py          # Diagnosis API test script
│
├── fixtures/                      # Test data and generation
│   ├── __init__.py
│   ├── create_test_data.py        # Python script to generate test data
│   └── create_test_data.sql       # SQL for test data
│
├── scripts/                       # Helper bash/shell scripts
│   ├── __init__.py
│   └── run_diagnosis_test.sh      # Diagnosis test runner
│
├── conftest.py                    # Pytest shared fixtures
├── test_main.py                   # Existing test
├── __init__.py
├── README.md                      # Full testing guide
└── ORGANIZATION.md               # This file

```

## Files Moved

| Original Location | New Location | Purpose |
|------------------|--------------|---------|
| `/create_test_data.py` | `tests/fixtures/` | Generate test meal/symptom data |
| `/create_test_data.sql` | `tests/fixtures/` | SQL version of test data |
| `/test_diagnosis.py` | `tests/integration/` | Diagnosis API test |
| `/run_diagnosis_test.sh` | `tests/scripts/` | Bash test runner |

## Quick Commands

```bash
# Generate test data
python tests/fixtures/create_test_data.py

# Run diagnosis test script
python tests/integration/test_diagnosis.py

# Run diagnosis bash test
bash tests/scripts/run_diagnosis_test.sh

# Run all pytest tests
pytest

# Run only unit tests (when we have them)
pytest tests/unit/

# Run only integration tests
pytest tests/integration/
```

## Next Steps for Test Coverage

### Priority 1: Unit Tests
- [ ] `tests/unit/services/test_confidence_scoring.py` - Test confidence calculation logic
- [ ] `tests/unit/services/test_correlation_analysis.py` - Test temporal correlation queries
- [ ] `tests/unit/models/test_diagnosis_result.py` - Test model validations

### Priority 2: Integration Tests
- [ ] `tests/integration/test_diagnosis_api.py` - Convert test_diagnosis.py to proper pytest
- [ ] `tests/integration/test_meals_api.py` - Test meal creation/update/delete
- [ ] `tests/integration/test_symptoms_api.py` - Test symptom logging

### Priority 3: Edge Cases
- [ ] Empty data scenarios
- [ ] Invalid input validation
- [ ] Error handling and recovery
- [ ] Concurrent request handling

### Priority 4: Performance
- [ ] Load testing for diagnosis with large datasets
- [ ] Query optimization verification
- [ ] Claude API rate limiting

## Configuration

Pytest is configured in `/pytest.ini`:
- Test discovery: `tests/` directory (recursive)
- Pattern: `test_*.py` files
- Verbose output enabled
- Strict marker mode
