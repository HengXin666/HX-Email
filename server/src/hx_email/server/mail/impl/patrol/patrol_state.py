"""巡检状态模型与事件缓冲 (线程安全), 供巡检管理器与路由共享。"""

from __future__ import annotations

import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from hx_email.config import Settings
from hx_email.server.settings_service import get_setting

# 终态: 巡检结束后可查询状态, 新任务启动时自动覆盖旧任务
TERMINAL_STATES: frozenset[str] = frozenset({"done", "error", "stopped"})
EVENT_BUFFER_LIMIT: int = 1000
MODE_LABELS: dict[str, str] = {
    "all": "全部",
    "failed": "刷新失败",
    "group": "分组",
    "ungrouped": "未分组",
    "selected": "选中",
}

CONCURRENT_WORKERS_DEFAULT: int = 8
CONCURRENT_WORKERS_MAX: int = 64


@dataclass(frozen=True)
class PatrolSnapshot:
    """巡检状态快照 (JSON 序列化友好)。"""

    status: str
    mode: str
    mode_label: str
    group_id: int | None
    total: int
    current: int
    success: int
    failed: int
    email: str
    started_at: str | None
    finished_at: str | None
    error: str

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "mode": self.mode,
            "mode_label": self.mode_label,
            "group_id": self.group_id,
            "total": self.total,
            "current": self.current,
            "success": self.success,
            "failed": self.failed,
            "email": self.email,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }


@dataclass
class _Patrol:
    settings: Settings
    user_id: int
    mode: str
    mode_label: str
    group_id: int | None
    status: str = "starting"
    total: int = 0
    current: int = 0
    success: int = 0
    failed: int = 0
    email: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    error: str = ""
    events: deque[tuple[int, dict[str, object]]] = field(default_factory=deque)
    _seq: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _pause: threading.Event = field(default_factory=threading.Event)
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None

    def snapshot(self) -> PatrolSnapshot:
        with self._lock:
            return PatrolSnapshot(
                status=self.status,
                mode=self.mode,
                mode_label=self.mode_label,
                group_id=self.group_id,
                total=self.total,
                current=self.current,
                success=self.success,
                failed=self.failed,
                email=self.email,
                started_at=self.started_at,
                finished_at=self.finished_at,
                error=self.error,
            )

    def append_event(self, event: dict[str, object]) -> None:
        with self._lock:
            self._seq += 1
            self.events.append((self._seq, event))
            if len(self.events) > EVENT_BUFFER_LIMIT:
                self.events.popleft()

    def events_since(self, seq: int) -> list[tuple[int, dict[str, object]]]:
        with self._lock:
            return [entry for entry in self.events if entry[0] > seq]


class ParallelProgress:
    """线程安全并发计数: done/success/fail 与 current 序号。"""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._done: int = 0
        self._success: int = 0
        self._fail: int = 0

    def advance(self, ok: bool) -> int:
        with self._lock:
            self._done += 1
            if ok:
                self._success += 1
            else:
                self._fail += 1
            return self._done

    @property
    def done_count(self) -> int:
        with self._lock:
            return self._done

    @property
    def success_count(self) -> int:
        with self._lock:
            return self._success

    @property
    def fail_count(self) -> int:
        with self._lock:
            return self._fail


def concurrent_workers(settings: Settings) -> int:
    """并发刷新 worker 数 (settings 可配 refresh_concurrent_workers, 默认 8)。"""
    try:
        value: int = int(str(get_setting(settings, "refresh_concurrent_workers", "8") or "8"))
    except ValueError:
        value = CONCURRENT_WORKERS_DEFAULT
    return max(1, min(value, CONCURRENT_WORKERS_MAX))


def stagger_sleep(settings: Settings) -> None:
    """批量刷新错峰: 每账号随机延迟 1..max 秒 (默认 20)。

    20260823 实测根因: 同批账号秒级连刷, 微软风控引擎把该簇账号一起标为
    compromised(security-interrupt for collecting proof), 随机错峰打散聚类特征.
    """
    try:
        max_seconds: int = int(
            str(get_setting(settings, "refresh_stagger_max_seconds", "20") or "20")
        )
    except ValueError:
        max_seconds = 20
    if max_seconds <= 0:
        return
    time.sleep(random.uniform(1.0, float(max(1, max_seconds))))
