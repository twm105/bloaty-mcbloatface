"""Test fixtures for Bloaty McBloatface."""

from tests.fixtures.api_cache import (
    cached_api_response,
    clear_cache,
    get_cached_files,
    set_cache_enabled,
    get_cache_enabled,
)
from tests.fixtures.mocks import (
    MockClaudeService,
    create_mock_with_error,
    create_mock_for_meal_analysis,
    create_mock_for_diagnosis,
)

__all__ = [
    "cached_api_response",
    "clear_cache",
    "get_cached_files",
    "set_cache_enabled",
    "get_cache_enabled",
    "MockClaudeService",
    "create_mock_with_error",
    "create_mock_for_meal_analysis",
    "create_mock_for_diagnosis",
]
