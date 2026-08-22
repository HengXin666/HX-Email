"""Settings validation helpers (20260823, settings_service 拆分)."""

from __future__ import annotations

from urllib.parse import urlparse


def validate_callback_url(value: str, field_name: str) -> None:
    """Require an explicit HTTP(S) callback URL."""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be an http:// or https:// URL")
