"""Simple in-memory TTL cache for overview statistics.

Maintains a module-level dict with (timestamp, value) tuples.
Entries expire after _CACHE_TTL seconds.
"""

from __future__ import annotations

import time

_CACHE: dict[str, tuple[float, object]] = {}
_CACHE_TTL: float = 30.0


def _get_cached(cache_key: str) -> object | None:
    """Return a cached value if it is still fresh, otherwise None."""
    entry = _CACHE.get(cache_key)
    if entry is not None:
        timestamp, value = entry
        if time.time() - timestamp < _CACHE_TTL:
            return value
        del _CACHE[cache_key]
    return None


def _set_cached(cache_key: str, value: object) -> None:
    """Store a value in the cache with current timestamp."""
    _CACHE[cache_key] = (time.time(), value)
