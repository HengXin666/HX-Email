"""QQ 空间轮询: 空间没有推送, 只能定时拉; 这里是唯一的拉取循环.

一个守护线程, 启动时只有在某个 QQ 实例配置了 ``qzone_watch`` 才真正去拉; 没有实例关注空间时
每 10 分钟醒一次看配置, 不发任何请求. 每个实例按自己的间隔 (``qzone_poll_minutes``, 不低于 5 分钟,
叠加 20% 抖动) 拉取, 遇到节流或风控把间隔翻倍到最多 60 分钟, 成功一次恢复.
"""

from __future__ import annotations

import logging
import random
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Final

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.gateway.impl.breaker import BREAKER
from hx_email.server.gateway.listen import store_envelopes
from hx_email.server.gateway.providers import HUB, InstanceRow, load_instance
from hx_email.server.router.providers.impl.qzone.qzone_contract import (
    MAX_WATCHED_SPACES,
    POLL_DEFAULT_MINUTES,
    POLL_JITTER_RATIO,
    POLL_MAX_BACKOFF_MINUTES,
    POLL_MIN_MINUTES,
    QzoneError,
)

LOGGER: logging.Logger = logging.getLogger("hx_email.gateway.qzone_poll")
IDLE_SECONDS: Final[float] = 600.0
MIN_SLEEP_SECONDS: Final[float] = 30.0


@dataclass
class PollState:
    next_at: float = 0.0
    backoff_minutes: int = 0


def watch_list(config: dict[str, str]) -> list[str]:
    """``qzone_watch`` 是逗号分隔的 QQ 号, 可写 ``self``; 去重后最多 5 个."""
    found: list[str] = []
    for part in config.get("qzone_watch", "").split(","):
        owner: str = part.strip()
        if (owner == "self" or owner.isdigit()) and owner not in found:
            found.append(owner)
    return found[:MAX_WATCHED_SPACES]


def interval_minutes(config: dict[str, str]) -> int:
    text: str = config.get("qzone_poll_minutes", "").strip()
    value: int = int(text) if text.isdigit() else POLL_DEFAULT_MINUTES
    return max(value, POLL_MIN_MINUTES)


def watching_instances(settings: Settings) -> list[InstanceRow]:
    """在线且配置了关注空间的 QQ 实例."""
    with connect(settings) as connection:
        rows: list[sqlite3.Row] = connection.execute(
            "SELECT id FROM messaging_instances WHERE kind = 'qq' ORDER BY id"
        ).fetchall()
    found: list[InstanceRow] = []
    for row in rows:
        instance: InstanceRow | None = load_instance(settings, int(row["id"]))
        if instance is not None and instance.status == "online" and watch_list(instance.config):
            found.append(instance)
    return found


# 空间只能拉: 间隔下限 5 分钟加抖动, 节流与风控翻倍退避, 风控同时喂给出站熔断
# 决策记录: .agents/notes/implemented/feature/2026-11-09-qzone-provider.md
def poll_instance(settings: Settings, instance: InstanceRow) -> tuple[int, QzoneError | None]:
    """拉一个实例关注的全部空间; 返回新入库条数与遇到的第一个错误 (遇错即停)."""
    provider = HUB.qzone_for(settings, instance)
    stored: int = 0
    for owner in watch_list(instance.config):
        try:
            stored += store_envelopes(settings, instance.id, provider.poll(owner))
        except QzoneError as error:
            if error.result.risk_signal:
                BREAKER.record_risk(instance.id)
            return stored, error
    return stored, None


class QzonePoller:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng: random.Random = rng or random.Random()
        self.states: dict[int, PollState] = {}
        self.wake_event: threading.Event = threading.Event()
        self.lock: threading.Lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.settings: Settings | None = None

    def start(self, settings: Settings) -> None:
        self.settings = settings
        with self.lock:
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self.run, name="qzone-poll", daemon=True)
                self.thread.start()

    def run(self) -> None:
        while True:
            delay: float = IDLE_SECONDS
            if self.settings is not None:
                try:
                    delay = self.round(self.settings, time.monotonic())
                except Exception:  # pragma: no cover - keep the thread alive
                    LOGGER.exception("qzone poll round failed")
            self.wake_event.wait(timeout=delay)
            self.wake_event.clear()

    def round(self, settings: Settings, now: float) -> float:
        """拉所有到期的实例; 返回距下一次到期的秒数."""
        instances: list[InstanceRow] = watching_instances(settings)
        live: set[int] = {instance.id for instance in instances}
        for stale in set(self.states) - live:
            self.states.pop(stale)
        next_due: float = now + IDLE_SECONDS
        for instance in instances:
            state: PollState = self.states.setdefault(instance.id, PollState())
            if state.next_at <= now:
                stored, error = poll_instance(settings, instance)
                self.schedule(state, interval_minutes(instance.config), error, now)
                LOGGER.info("qzone poll instance=%s stored=%s error=%s", instance.id, stored, error)
            next_due = min(next_due, state.next_at)
        return max(MIN_SLEEP_SECONDS, next_due - now)

    def schedule(self, state: PollState, base: int, error: QzoneError | None, now: float) -> None:
        if error is None:
            state.backoff_minutes = 0
        else:
            doubled: int = max(state.backoff_minutes, base) * 2
            state.backoff_minutes = min(doubled, POLL_MAX_BACKOFF_MINUTES)
        minutes: int = state.backoff_minutes or base
        jitter: float = 1.0 + self.rng.uniform(-POLL_JITTER_RATIO, POLL_JITTER_RATIO)
        state.next_at = now + minutes * 60.0 * jitter


QZONE_POLLER: QzonePoller = QzonePoller()
