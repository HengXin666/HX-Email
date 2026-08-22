"""Refresh scheduler registry + settings getters (20260823)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hx_email.config import Settings
from hx_email.server.settings_service import get_setting

if TYPE_CHECKING:
    from hx_email.server.mail.impl.refresh.scheduler import TokenRefreshScheduler

DEFAULT_INTERVAL_SECONDS: int = 3600
MIN_INTERVAL_SECONDS: int = 60
MAX_INTERVAL_SECONDS: int = 86_400

REFRESH_SCHEDULERS: dict[str, TokenRefreshScheduler] = {}


def register_refresh_scheduler(settings: Settings, scheduler: TokenRefreshScheduler) -> None:
    REFRESH_SCHEDULERS[str(settings.data_dir)] = scheduler


def unregister_refresh_scheduler(settings: Settings, scheduler: TokenRefreshScheduler) -> None:
    REFRESH_SCHEDULERS.pop(str(settings.data_dir), None)


def wake_refresh_scheduler(settings: Settings) -> None:
    scheduler = REFRESH_SCHEDULERS.get(str(settings.data_dir))
    if scheduler is not None:
        scheduler.wake()


def refresh_schedule_enabled(settings: Settings) -> bool:
    return get_setting(settings, "refresh_schedule_enabled", "true").lower() == "true"


def refresh_schedule_interval_seconds(settings: Settings) -> int:
    try:
        value: int = int(get_setting(settings, "refresh_schedule_interval_seconds", "3600"))
    except ValueError:
        value = DEFAULT_INTERVAL_SECONDS
    return max(MIN_INTERVAL_SECONDS, min(value, MAX_INTERVAL_SECONDS))


def refresh_stagger_max_seconds(settings: Settings) -> int:
    try:
        return max(0, int(get_setting(settings, "refresh_stagger_max_seconds", "20")))
    except ValueError:
        return 20


def get_refresh_scheduler_status(settings: Settings) -> dict[str, object]:
    """Expose scheduler runtime status (registry lookup, mirrors polling)."""
    scheduler = REFRESH_SCHEDULERS.get(str(settings.data_dir))
    if scheduler is None:
        return {
            "running": False,
            "enabled": refresh_schedule_enabled(settings),
            "interval_seconds": refresh_schedule_interval_seconds(settings),
            "stagger_max_seconds": refresh_stagger_max_seconds(settings),
            "last_run": "",
            "next_run": "",
            "last_error": "scheduler not started",
            "last_summary": {},
        }
    return scheduler.status()
