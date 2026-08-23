"""Master-slave sync configuration persisted in the settings table.

The sync URL/token/interval were previously env-only (HX_EMAIL_SYNC_*). They
now live in the settings table so an admin can manage them from the settings
page; env values are still seeded once as initial defaults.
"""

from urllib.parse import urlparse

from hx_email.config import Settings
from hx_email.server.settings_service import get_setting, set_setting

SYNC_SETTING_KEYS: frozenset[str] = frozenset(
    {
        "sync_url",
        "sync_token",
        "sync_interval_seconds",
        "sync_full_interval_seconds",
    }
)
DEFAULT_SYNC_INTERVAL_SECONDS: int = 300
DEFAULT_FULL_INTERVAL_SECONDS: int = 86_400  # 24h
MAX_SYNC_INTERVAL_SECONDS: int = 86_400
MAX_FULL_INTERVAL_SECONDS: int = 30 * 86_400  # 30d


def validate_sync_config(merged: dict[str, str]) -> None:
    """Validate a merged settings dict: url/token must be a pair, intervals in range."""
    url: str = merged.get("sync_url", "")
    token: str = merged.get("sync_token", "")
    if bool(url) != bool(token):
        raise ValueError("sync_url and sync_token must be set together")
    if url:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("sync_url must be an http:// or https:// URL")
    interval_raw: str = merged.get("sync_interval_seconds", "")
    if not interval_raw.isdigit():
        if interval_raw:
            raise ValueError("sync_interval_seconds must be an integer")
        return
    interval: int = int(interval_raw)
    if not 0 <= interval <= MAX_SYNC_INTERVAL_SECONDS:
        raise ValueError(f"sync_interval_seconds must be between 0 and {MAX_SYNC_INTERVAL_SECONDS}")
    full_raw: str = merged.get("sync_full_interval_seconds", "")
    if not full_raw.isdigit():
        if full_raw:
            raise ValueError("sync_full_interval_seconds must be an integer")
        return
    full_interval: int = int(full_raw)
    if not 0 <= full_interval <= MAX_FULL_INTERVAL_SECONDS:
        raise ValueError(
            f"sync_full_interval_seconds must be between 0 and {MAX_FULL_INTERVAL_SECONDS}"
        )


def seed_sync_config_from_env(settings: Settings) -> None:
    """One-time seed: copy env values into the settings table when unset."""
    for key, env_value in (
        ("sync_url", settings.sync_url),
        ("sync_token", settings.sync_token),
        ("sync_interval_seconds", str(settings.sync_interval_seconds)),
    ):
        if env_value and not get_setting(settings, key, ""):
            set_setting(settings, key, env_value)
    if not get_setting(settings, "sync_full_interval_seconds", ""):
        set_setting(settings, "sync_full_interval_seconds", str(DEFAULT_FULL_INTERVAL_SECONDS))


def reload_sync_settings(settings: Settings) -> None:
    """Refresh the Settings object from the table (empty means sync disabled)."""
    settings.sync_url = get_setting(settings, "sync_url", "")
    settings.sync_token = get_setting(settings, "sync_token", "")
    interval_raw: str = get_setting(settings, "sync_interval_seconds", "")
    settings.sync_interval_seconds = (
        int(interval_raw) if interval_raw.isdigit() else DEFAULT_SYNC_INTERVAL_SECONDS
    )
    full_raw: str = get_setting(settings, "sync_full_interval_seconds", "")
    settings.sync_full_interval_seconds = (
        int(full_raw) if full_raw.isdigit() else DEFAULT_FULL_INTERVAL_SECONDS
    )


def apply_sync_config(settings: Settings) -> None:
    """After a settings save: refresh config and restart the sync scheduler."""
    reload_sync_settings(settings)
    from hx_email.server.sync.scheduler import restart_sync_scheduler

    restart_sync_scheduler(settings)
