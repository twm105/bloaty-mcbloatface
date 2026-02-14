"""API response caching for cost-free eval re-runs."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


CACHE_DIR = Path(__file__).parent / "api_cache"


class CacheManager:
    """Manage cached API responses for eval runs.

    Caches are keyed by a hash of the method name and stable kwargs,
    allowing re-runs without incurring API costs.
    """

    def __init__(self, enabled: bool = True, cache_dir: Path = CACHE_DIR):
        self.enabled = enabled
        self.cache_dir = cache_dir

        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, method: str, **kwargs) -> str:
        """Generate deterministic cache key from method and kwargs.

        Args:
            method: API method name (e.g., 'analyze_meal_image')
            **kwargs: Stable parameters (image_path, model, etc.)

        Returns:
            16-character hash string
        """
        # Sort kwargs for deterministic ordering
        stable_kwargs = {k: v for k, v in sorted(kwargs.items())}
        data = f"{method}:{json.dumps(stable_kwargs, sort_keys=True)}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def _cache_file(self, method: str, key: str) -> Path:
        """Get cache file path for a method and key."""
        return self.cache_dir / f"{method}_{key}.json"

    def get(self, method: str, **kwargs) -> dict | None:
        """Retrieve cached response if available.

        Args:
            method: API method name
            **kwargs: Request parameters

        Returns:
            Cached response dict, or None if not cached
        """
        if not self.enabled:
            return None

        key = self._cache_key(method, **kwargs)
        cache_file = self._cache_file(method, key)

        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    cached = json.load(f)
                    return cached.get("response")
            except (json.JSONDecodeError, KeyError):
                # Invalid cache, ignore
                return None

        return None

    def set(self, method: str, response: Any, **kwargs) -> None:
        """Cache an API response.

        Args:
            method: API method name
            response: Response data to cache (must be JSON-serializable)
            **kwargs: Request parameters
        """
        if not self.enabled:
            return

        key = self._cache_key(method, **kwargs)
        cache_file = self._cache_file(method, key)

        cache_data = {
            "method": method,
            "kwargs": kwargs,
            "response": response,
            "cached_at": datetime.utcnow().isoformat(),
        }

        with open(cache_file, "w") as f:
            json.dump(cache_data, f, indent=2, default=str)

    def clear(self, method: str | None = None) -> int:
        """Clear cached responses.

        Args:
            method: If provided, only clear caches for this method.
                    If None, clear all caches.

        Returns:
            Number of cache files deleted
        """
        if not self.cache_dir.exists():
            return 0

        count = 0
        pattern = f"{method}_*.json" if method else "*.json"

        for cache_file in self.cache_dir.glob(pattern):
            cache_file.unlink()
            count += 1

        return count

    def stats(self) -> dict:
        """Get cache statistics.

        Returns:
            Dict with cache stats (file_count, total_size_bytes, methods)
        """
        if not self.cache_dir.exists():
            return {"file_count": 0, "total_size_bytes": 0, "methods": {}}

        files = list(self.cache_dir.glob("*.json"))
        methods: dict[str, int] = {}

        for f in files:
            # Extract method from filename (method_hash.json)
            parts = f.stem.rsplit("_", 1)
            if len(parts) == 2:
                method = parts[0]
                methods[method] = methods.get(method, 0) + 1

        total_size = sum(f.stat().st_size for f in files)

        return {
            "file_count": len(files),
            "total_size_bytes": total_size,
            "methods": methods,
        }
