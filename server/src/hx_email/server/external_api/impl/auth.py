"""API Key authentication and rate limiting for external API."""

import json
import time
from typing import Any

from fastapi import HTTPException, status

from hx_email.config import Settings
from hx_email.server.settings_service import get_setting

# In-memory rate limit tracking: {api_key: [timestamp, ...]}
_rate_limit_store: dict[str, list[float]] = {}


def _clean_expired_timestamps(timestamps: list[float], window_seconds: float) -> list[float]:
    """Remove timestamps outside the rate limit window."""
    now = time.monotonic()
    return [ts for ts in timestamps if now - ts < window_seconds]


def validate_api_key(settings: Settings, api_key: str) -> bool:
    """Check X-API-Key against stored keys.

    Supports both a single external_api_key and a JSON array external_api_keys.
    """
    if not api_key:
        return False
    single_key: str = get_setting(settings, "external_api_key", "")
    if single_key and single_key == api_key:
        return True
    keys_json: str = get_setting(settings, "external_api_keys", "[]")
    try:
        keys_list: list[Any] = json.loads(keys_json)
    except (json.JSONDecodeError, TypeError):
        return False
    return api_key in keys_list


def check_rate_limit(settings: Settings, api_key: str) -> bool:
    """Check rate limit per minute. Uses an in-memory dict with timestamps."""
    limit_str: str = get_setting(settings, "external_api_rate_limit_per_minute", "60")
    try:
        limit: int = int(limit_str)
    except (ValueError, TypeError):
        limit = 60
    if limit <= 0:
        return True
    window: float = 60.0
    now: float = time.monotonic()
    store = _rate_limit_store
    if api_key not in store:
        store[api_key] = []
    store[api_key] = _clean_expired_timestamps(store[api_key], window)
    if len(store[api_key]) >= limit:
        return False
    store[api_key].append(now)
    return True


def require_api_key(settings: Settings, authorization: str | None) -> str:
    """Extract X-API-Key from header, validate, check rate limit.

    Returns the valid API key string.
    Raises HTTPException(401) if key is missing or invalid.
    Raises HTTPException(429) if rate limit exceeded.
    """
    api_key: str = (authorization or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    if not validate_api_key(settings, api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    if not check_rate_limit(settings, api_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )
    return api_key
