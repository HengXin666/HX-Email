"""巡检状态模型与事件缓冲 (线程安全), 供巡检管理器与路由共享。"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field

from hx_email.config import Settings

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
