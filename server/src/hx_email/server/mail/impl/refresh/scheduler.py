"""后台定时随机刷新调度器: 按 settings 周期刷新全部账号的 OAuth token.

20260823 用户需求: 快速巡检只读状态, 刷新交给邮箱平台定时做, 且每个账号
随机错峰(refresh_stagger_max_seconds)避免秒级连刷触发微软聚类标记.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail.impl.patrol.patrol_manager import manager as patrol_manager
from hx_email.server.mail.impl.refresh.settings import (
    refresh_schedule_enabled,
    refresh_schedule_interval_seconds,
    refresh_stagger_max_seconds,
    register_refresh_scheduler,
    unregister_refresh_scheduler,
)
from hx_email.server.mail.verification import MailboxProvider

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS: int = 3600
MIN_INTERVAL_SECONDS: int = 60
MAX_INTERVAL_SECONDS: int = 86_400
DISABLED_RECHECK_SECONDS: int = 5


class TokenRefreshScheduler:
    """Own one stoppable refresh thread for an application instance."""

    def __init__(self, settings: Settings, mailbox_provider: MailboxProvider) -> None:
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
        self.thread = threading.Thread(target=self.run, daemon=True, name="token-refresher")
        self.thread.start()
        register_refresh_scheduler(self.settings, self)

    def stop(self) -> None:
        self.stop_event.set()
        self.wake_event.set()
        if self.thread is not None:
            self.thread.join(timeout=5)
        unregister_refresh_scheduler(self.settings, self)

    def wake(self) -> None:
        self.wake_event.set()

    def run(self) -> None:
        logger.info("Token refresh scheduler started")
        while not self.stop_event.is_set():
            if not refresh_schedule_enabled(self.settings):
                self.update_next_run("")
                self.wait(DISABLED_RECHECK_SECONDS)
                continue
            interval_seconds: int = refresh_schedule_interval_seconds(self.settings)
            self.run_once()
            next_run: datetime = datetime.now(UTC) + timedelta(seconds=interval_seconds)
            self.update_next_run(next_run.isoformat())
            self.wait(interval_seconds)

    def run_once(self) -> dict[str, Any]:
        started_at: str = datetime.now(UTC).isoformat()
        try:
            with connect(self.settings) as connection:
                rows = connection.execute(
                    "SELECT DISTINCT user_id FROM email_accounts "
                    "WHERE status = 'active' AND refresh_token != ''"
                ).fetchall()
            user_ids: list[int] = [int(row["user_id"]) for row in rows]
            total: int = 0
            for user_id in user_ids:
                # 后台 patrol 并发刷新, 不阻塞调度线程; 已有任务在跑则跳过。
                if patrol_manager.is_running(user_id):
                    continue
                started: bool = patrol_manager.start(self.settings, user_id, "all")
                if not started:
                    continue
                snapshot = patrol_manager.snapshot(user_id)
                total += snapshot.total
            summary: dict[str, Any] = {"total": total, "started_users": len(user_ids)}
            with self.state_lock:
                self.last_run = started_at
                self.last_summary = summary
                self.last_error = ""
            return summary
        except Exception as error:
            logger.exception("Automatic token refresh failed")
            with self.state_lock:
                self.last_run = started_at
                self.last_error = str(error)
            return {"error": str(error)}

    def status(self) -> dict[str, object]:
        with self.state_lock:
            return {
                "running": self.thread is not None and self.thread.is_alive(),
                "enabled": refresh_schedule_enabled(self.settings),
                "interval_seconds": refresh_schedule_interval_seconds(self.settings),
                "stagger_max_seconds": refresh_stagger_max_seconds(self.settings),
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
