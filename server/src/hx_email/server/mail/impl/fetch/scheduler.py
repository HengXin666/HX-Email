"""Runtime scheduler for settings-driven automatic mail polling."""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from hx_email.config import Settings
from hx_email.server.mail.impl.email_fetch_service import fetch_all_active_accounts
from hx_email.server.mail.verification import MailboxProvider
from hx_email.server.notifications import retry_pending_deliveries
from hx_email.server.settings_service import get_setting

logger = logging.getLogger(__name__)

MIN_POLLING_INTERVAL_SECONDS: int = 3
MAX_POLLING_INTERVAL_SECONDS: int = 86_400
DISABLED_RECHECK_SECONDS: int = 1


class MailPollingScheduler:
    """Own one stoppable polling thread for an application instance."""

    def __init__(
        self,
        settings: Settings,
        mailbox_provider: MailboxProvider,
    ) -> None:
        self.settings: Settings = settings
        self.mailbox_provider: MailboxProvider = mailbox_provider
        self.stop_event: threading.Event = threading.Event()
        self.wake_event: threading.Event = threading.Event()
        self.thread: threading.Thread | None = None
        self.state_lock: threading.Lock = threading.Lock()
        self.last_run: str = ""
        self.next_run: str = ""
        self.last_summary: dict[str, Any] = {}
        self.last_error: str = ""

    def start(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.run, daemon=True, name="mail-poller")
        self.thread.start()
        register_polling_scheduler(self.settings, self)

    def stop(self) -> None:
        self.stop_event.set()
        self.wake_event.set()
        if self.thread is not None:
            self.thread.join(timeout=5)
        unregister_polling_scheduler(self.settings, self)

    def wake(self) -> None:
        self.wake_event.set()

    def run(self) -> None:
        logger.info("Mail polling scheduler started")
        while not self.stop_event.is_set():
            if not polling_enabled(self.settings):
                self.update_next_run("")
                self.wait(DISABLED_RECHECK_SECONDS)
                continue
            interval_seconds: int = polling_interval_seconds(self.settings)
            self.run_once()
            next_run: datetime = datetime.now(UTC) + timedelta(seconds=interval_seconds)
            self.update_next_run(next_run.isoformat())
            self.wait(interval_seconds)

    def run_once(self) -> dict[str, Any]:
        started_at: str = datetime.now(UTC).isoformat()
        try:
            summary: dict[str, Any] = fetch_all_active_accounts(
                self.settings,
                self.mailbox_provider,
            )
            summary["delivery_retry"] = retry_pending_deliveries(self.settings).as_dict()
            with self.state_lock:
                self.last_run = started_at
                self.last_summary = summary
                self.last_error = ""
            return summary
        except Exception as error:
            logger.exception("Automatic mail polling failed")
            with self.state_lock:
                self.last_run = started_at
                self.last_error = str(error)
            return {"error": str(error)}

    def status(self) -> dict[str, object]:
        with self.state_lock:
            return {
                "running": self.thread is not None and self.thread.is_alive(),
                "enabled": polling_enabled(self.settings),
                "interval_seconds": polling_interval_seconds(self.settings),
                "last_run": self.last_run,
                "next_run": self.next_run,
                "last_error": self.last_error,
                "last_summary": dict(self.last_summary),
            }

    def update_next_run(self, value: str) -> None:
        with self.state_lock:
            self.next_run = value

    def wait(self, timeout_seconds: int) -> None:
        self.wake_event.wait(timeout_seconds)
        self.wake_event.clear()


SCHEDULER_LOCK: threading.Lock = threading.Lock()
SCHEDULERS: dict[str, MailPollingScheduler] = {}


def polling_enabled(settings: Settings) -> bool:
    return get_setting(settings, "enable_auto_polling", "false").lower() == "true"


def polling_interval_seconds(settings: Settings) -> int:
    raw_value: str = get_setting(settings, "polling_interval", "30")
    try:
        parsed_value: int = int(raw_value)
    except ValueError:
        parsed_value = 30
    return min(max(parsed_value, MIN_POLLING_INTERVAL_SECONDS), MAX_POLLING_INTERVAL_SECONDS)


def scheduler_key(settings: Settings) -> str:
    return str(settings.database_path.resolve())


def register_polling_scheduler(
    settings: Settings,
    scheduler: MailPollingScheduler,
) -> None:
    with SCHEDULER_LOCK:
        SCHEDULERS[scheduler_key(settings)] = scheduler


def unregister_polling_scheduler(
    settings: Settings,
    scheduler: MailPollingScheduler,
) -> None:
    with SCHEDULER_LOCK:
        key: str = scheduler_key(settings)
        if SCHEDULERS.get(key) is scheduler:
            SCHEDULERS.pop(key, None)


def wake_polling_scheduler(settings: Settings) -> None:
    with SCHEDULER_LOCK:
        scheduler: MailPollingScheduler | None = SCHEDULERS.get(scheduler_key(settings))
    if scheduler is not None:
        scheduler.wake()


def get_polling_status(settings: Settings) -> dict[str, object]:
    with SCHEDULER_LOCK:
        scheduler: MailPollingScheduler | None = SCHEDULERS.get(scheduler_key(settings))
    if scheduler is None:
        return {
            "running": False,
            "enabled": polling_enabled(settings),
            "interval_seconds": polling_interval_seconds(settings),
            "last_run": "",
            "next_run": "",
            "last_error": "",
            "last_summary": {},
        }
    return scheduler.status()
