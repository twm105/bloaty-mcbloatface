"""
API Response Caching for Tests.

This module provides caching functionality for API responses to:
- Avoid API costs during test runs
- Ensure deterministic test results
- Speed up test execution

Usage:
    @cached_api_response
    async def analyze_meal_image(image_path: str) -> dict:
        # Make actual API call
        return result
"""
import hashlib
import json
from pathlib import Path
from functools import wraps
from datetime import datetime
from typing import Any, Callable, Optional, TypeVar, Union
import asyncio

# Cache directory
CACHE_DIR = Path(__file__).parent / "api_responses"
CACHE_DIR.mkdir(exist_ok=True)

# Global flag for cache control (set via pytest fixtures)
# Defaults to False for production safety - enabled via pytest fixtures
_use_cache = False


def set_cache_enabled(enabled: bool):
    """Enable or disable cache globally."""
    global _use_cache
    _use_cache = enabled


def get_cache_enabled() -> bool:
    """Check if cache is enabled."""
    return _use_cache


def _generate_cache_key(func_name: str, args: tuple, kwargs: dict) -> str:
    """
    Generate a deterministic cache key from function name and arguments.

    Handles:
    - File paths (hashes file content instead of path)
    - Complex nested structures
    - Non-serializable objects (converts to string representation)
    """
    key_parts = [func_name]

    # Process args
    for arg in args:
        if isinstance(arg, (str, Path)) and Path(arg).exists():
            # For file paths, hash the file content
            try:
                with open(arg, "rb") as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()[:16]
                key_parts.append(f"file:{file_hash}")
            except (IOError, PermissionError):
                key_parts.append(str(arg))
        else:
            key_parts.append(_serialize_value(arg))

    # Process kwargs (sorted for determinism)
    for key in sorted(kwargs.keys()):
        value = kwargs[key]
        key_parts.append(f"{key}={_serialize_value(value)}")

    # Generate hash
    combined = ":".join(key_parts)
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def _serialize_value(value: Any) -> str:
    """Serialize a value for cache key generation."""
    if isinstance(value, (str, int, float, bool, type(None))):
        return str(value)
    elif isinstance(value, (list, tuple)):
        return f"[{','.join(_serialize_value(v) for v in value)}]"
    elif isinstance(value, dict):
        items = sorted(value.items())
        return f"{{{','.join(f'{k}:{_serialize_value(v)}' for k, v in items)}}}"
    else:
        return str(value)


def cached_api_response(func: Callable) -> Callable:
    """
    Decorator that caches API responses for test replay.

    Responses are stored as JSON files keyed by function name and arguments.
    Use --refresh-api-cache to refresh cached responses.

    Example:
        @cached_api_response
        async def analyze_meal_image(image_path: str) -> dict:
            # Make actual API call
            return {"ingredients": [...]}
    """
    @wraps(func)
    async def async_wrapper(*args, use_cache: Optional[bool] = None, **kwargs):
        # Determine whether to use cache
        should_use_cache = use_cache if use_cache is not None else get_cache_enabled()

        cache_key = _generate_cache_key(func.__name__, args, kwargs)
        cache_file = CACHE_DIR / f"{func.__name__}_{cache_key}.json"

        if should_use_cache and cache_file.exists():
            try:
                data = json.loads(cache_file.read_text())
                return data.get("response")
            except (json.JSONDecodeError, KeyError):
                pass  # Cache corrupted, regenerate

        # Make actual API call
        result = await func(*args, **kwargs)

        # Cache the response
        cache_data = {
            "request": {
                "function": func.__name__,
                "args_hash": cache_key,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            },
            "response": result
        }

        try:
            cache_file.write_text(json.dumps(cache_data, indent=2, default=str))
        except (IOError, TypeError) as e:
            # Non-fatal: just don't cache
            print(f"Warning: Could not cache response: {e}")

        return result

    @wraps(func)
    def sync_wrapper(*args, use_cache: Optional[bool] = None, **kwargs):
        # Determine whether to use cache
        should_use_cache = use_cache if use_cache is not None else get_cache_enabled()

        cache_key = _generate_cache_key(func.__name__, args, kwargs)
        cache_file = CACHE_DIR / f"{func.__name__}_{cache_key}.json"

        if should_use_cache and cache_file.exists():
            try:
                data = json.loads(cache_file.read_text())
                return data.get("response")
            except (json.JSONDecodeError, KeyError):
                pass

        # Make actual API call
        result = func(*args, **kwargs)

        # Cache the response
        cache_data = {
            "request": {
                "function": func.__name__,
                "args_hash": cache_key,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            },
            "response": result
        }

        try:
            cache_file.write_text(json.dumps(cache_data, indent=2, default=str))
        except (IOError, TypeError):
            pass

        return result

    # Return appropriate wrapper based on whether function is async
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper


def clear_cache(func_name: Optional[str] = None):
    """
    Clear cached responses.

    Args:
        func_name: If provided, only clear cache for this function.
                   If None, clear all cached responses.
    """
    if func_name:
        pattern = f"{func_name}_*.json"
    else:
        pattern = "*.json"

    for cache_file in CACHE_DIR.glob(pattern):
        try:
            cache_file.unlink()
        except OSError:
            pass


def get_cached_files(func_name: Optional[str] = None) -> list[Path]:
    """
    List cached response files.

    Args:
        func_name: If provided, only list cache files for this function.

    Returns:
        List of cache file paths.
    """
    if func_name:
        pattern = f"{func_name}_*.json"
    else:
        pattern = "*.json"

    return list(CACHE_DIR.glob(pattern))
