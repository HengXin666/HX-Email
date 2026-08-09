"""Periodic background sync scheduler, mirroring the mail polling scheduler."""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from hx_email.config import Settings
from hx_email.server.sync.service import SyncReport, run_sync

logger = logging.getLogger(__name__)

MIN_SYNC_INTERVAL_SECONDS: int = 30


class SyncScheduler:
    """Own one stoppable sync thread; runs immediately on start, then periodically."""

    def __init__(self, settings: Settings) -> None:
        self.settings: Settings = settings
        self.stop_event: threading.Event = threading.Event()
        self.thread: threading.Thread | None = None
        self.state_lock: threading.Lock = threading.Lock()
        self.last_run: str = ""
        self.next_run: str = ""
        self.last_error: str = ""
        self.last_summary: dict[str, Any] = {}

    def start(self) -> None:
        if not sync_configured(self.settings):
            return
        if self.thread is not None and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.run, daemon=True, name="mail-sync")
        self.thread.start()
        register_sync_scheduler(self.settings, self)

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=5)
        unregister_sync_scheduler(self.settings, self)

    def run(self) -> None:
        logger.info("Sync scheduler started")
        while not self.stop_event.is_set():
            self.run_once()
            if self.settings.sync_interval_seconds <= 0:
                self.stop_event.wait()
                break
            interval_seconds: int = max(
                self.settings.sync_interval_seconds, MIN_SYNC_INTERVAL_SECONDS
            )
            next_run: datetime = datetime.now(UTC) + timedelta(seconds=interval_seconds)
            with self.state_lock:
                self.next_run = next_run.isoformat()
            self.stop_event.wait(interval_seconds)

    def run_once(self) -> SyncReport:
        report: SyncReport = run_sync(self.settings)
        with self.state_lock:
            self.last_run = report.finished_at
            self.last_error = report.error
            self.last_summary = report.to_dict()
        if report.error:
            logger.warning("Sync round failed: %s", report.error)
        else:
            logger.info("Sync round completed")
        return report

    def status(self) -> dict[str, object]:
        with self.state_lock:
            return {
                "running": self.thread is not None and self.thread.is_alive(),
                "enabled": sync_configured(self.settings),
                "interval_seconds": self.settings.sync_interval_seconds,
                "last_run": self.last_run,
                "next_run": self.next_run,
                "last_error": self.last_error,
                "last_summary": dict(self.last_summary),
            }


def sync_configured(settings: Settings) -> bool:
    return bool(settings.sync_url.strip() and settings.sync_token.strip())


SCHEDULER_LOCK: threading.Lock = threading.Lock()
SCHEDULERS: dict[str, SyncScheduler] = {}


def scheduler_key(settings: Settings) -> str:
    return str(settings.database_path.resolve())


def register_sync_scheduler(settings: Settings, scheduler: SyncScheduler) -> None:
    with SCHEDULER_LOCK:
        SCHEDULERS[scheduler_key(settings)] = scheduler


def unregister_sync_scheduler(settings: Settings, scheduler: SyncScheduler) -> None:
    with SCHEDULER_LOCK:
        key: str = scheduler_key(settings)
        if SCHEDULERS.get(key) is scheduler:
            SCHEDULERS.pop(key, None)


def get_sync_status(settings: Settings) -> dict[str, object]:
    with SCHEDULER_LOCK:
        scheduler: SyncScheduler | None = SCHEDULERS.get(scheduler_key(settings))
    if scheduler is None:
        return {
            "running": False,
            "enabled": sync_configured(settings),
            "interval_seconds": settings.sync_interval_seconds,
            "last_run": "",
            "next_run": "",
            "last_error": "",
            "last_summary": {},
        }
    return scheduler.status()
