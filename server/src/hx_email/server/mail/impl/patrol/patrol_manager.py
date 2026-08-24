"""持久化巡检管理器 (per-user 全局单例)。

批量 Token 刷新在后台线程池中执行, 与 HTTP 连接解耦:
- 页面刷新/切换后巡检继续运行, 新页面可随时查询状态或重新订阅事件流
- 支持暂停 / 恢复 / 终止
- 事件带自增序号缓冲在内存, 断线重连时可回放补全进度
- 多账号并发刷新 (CONCURRENT_WORKERS, 默认 8) 显著缩短总耗时, 同时保留
  随机错峰避免秒级连刷触发微软风控聚类标记

状态模型见 patrol_state.py; 与 refresh_service 的同步 SSE 生成器并存,
后者保留给旧端点与外部同步调用 (均有测试覆盖)。
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import cast

from hx_email.config import Settings
from hx_email.server.mail.impl.oauth_tool import try_refresh_provider_oauth_token
from hx_email.server.mail.impl.patrol.patrol_state import (
    MODE_LABELS,
    TERMINAL_STATES,
    ParallelProgress,
    PatrolSnapshot,
    _Patrol,
)
from hx_email.server.mail.impl.patrol.patrol_state import (
    concurrent_workers as _concurrent_workers,
)
from hx_email.server.mail.impl.patrol.patrol_state import (
    stagger_sleep as _stagger_sleep,
)
from hx_email.server.mail.impl.patrol.refresh import fetch_accounts as _fetch_accounts
from hx_email.server.mail.impl.refresh.rounds import (
    create_refresh_round as _create_refresh_round,
)
from hx_email.server.mail.impl.refresh.rounds import (
    finish_refresh_round as _finish_refresh_round,
)
from hx_email.server.mail.impl.refresh_log_service import (
    insert_refresh_log as _insert_refresh_log,
)
from hx_email.server.mail.impl.refresh_log_service import now_iso as _now_iso

__all__ = ["PatrolSnapshot", "manager"]


class PatrolManager:
    """每用户至多一个巡检任务; 线程后台执行, 支持暂停/恢复/终止。"""

    def __init__(self) -> None:
        self._patrols: dict[int, _Patrol] = {}
        self._lock = threading.Lock()

    def is_running(self, user_id: int) -> bool:
        patrol = self._patrols.get(user_id)
        return patrol is not None and patrol.status in ("starting", "running", "paused")

    def start(
        self,
        settings: Settings,
        user_id: int,
        mode: str,
        group_id: int | None = None,
        account_ids: list[int] | None = None,
    ) -> bool:
        """启动巡检; 若已有进行中任务返回 False。"""
        with self._lock:
            if self.is_running(user_id):
                return False
            patrol = _Patrol(
                settings=settings,
                user_id=user_id,
                mode=mode,
                mode_label=MODE_LABELS.get(mode, mode),
                group_id=group_id,
            )
            self._patrols[user_id] = patrol
        try:
            accounts: list[dict[str, object]] = _fetch_accounts(
                settings, user_id, mode, group_id, account_ids
            )
        except Exception as error:  # 拉取失败直接进入终态
            patrol.status = "error"
            patrol.error = str(error)
            patrol.finished_at = _now_iso()
            patrol.append_event(
                {"type": "complete", "total": 0, "success": 0, "failed": 0, "error": str(error)}
            )
            return True
        patrol.total = len(accounts)
        patrol.started_at = _now_iso()
        patrol.status = "running"
        scope: str = f"{mode}:{group_id}" if group_id is not None else mode
        patrol.round_id = _create_refresh_round(settings, user_id, scope)
        patrol.append_event({"type": "start", "total": len(accounts)})
        patrol._thread = threading.Thread(
            target=self._run, args=(patrol, accounts), daemon=True, name=f"patrol-{user_id}"
        )
        patrol._thread.start()
        return True

    def _run(self, patrol: _Patrol, accounts: list[dict[str, object]]) -> None:
        total: int = len(accounts)
        try:
            workers: int = _concurrent_workers(patrol.settings)
            self._run_parallel(patrol, accounts, workers)
        except Exception as error:  # 巡检兜底, 状态写入快照
            self._finish_with_error(patrol, total, error)

    def _run_parallel(
        self,
        patrol: _Patrol,
        accounts: list[dict[str, object]],
        workers: int,
    ) -> None:
        """并发刷新: 每个账号一个 worker, 保留随机错峰, 进度计数线程安全。

        共享一个带锁的进度结构; 任一账号失败不影响其余账号 (逐个记录)。
        workers=1 时退化为串行, 行为与旧版一致。
        """
        total: int = len(accounts)
        progress = ParallelProgress()
        try:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="patrol-w") as pool:
                futures = [
                    pool.submit(self._refresh_worker, patrol, account, progress)
                    for account in accounts
                ]
                # 等待全部完成; 停止信号时不再启动新的, 已提交的逐个完成
                for future in futures:
                    if patrol._stop.is_set():
                        break
                    future.result(timeout=600)
        except Exception as error:  # 任一 worker 异常不影响整体状态
            self._finish_with_error(patrol, total, error)
            return
        stopped: bool = patrol._stop.is_set()
        with patrol._lock:
            patrol.status = "stopped" if stopped else "done"
            patrol.finished_at = _now_iso()
            patrol.current = progress.done_count
            patrol.success = progress.success_count
            patrol.failed = progress.fail_count
        _finish_refresh_round(
            patrol.settings,
            patrol.round_id,
            total,
            progress.success_count,
            progress.fail_count,
        )
        patrol.append_event(
            {
                "type": "complete",
                "total": total,
                "success": progress.success_count,
                "failed": progress.fail_count,
                "stopped": stopped,
            }
        )

    def _refresh_worker(
        self,
        patrol: _Patrol,
        account: dict[str, object],
        progress: ParallelProgress,
    ) -> None:
        """单账号刷新 worker: 错峰 + 刷新 + 记日志 + 进度事件。"""
        # 等待暂停 (暂停期间停止信号可打断)
        while patrol._pause.is_set() and not patrol._stop.is_set():
            time.sleep(0.3)
        if patrol._stop.is_set():
            return
        # 错峰: 每个账号随机延迟, 打散同一簇账号的连刷特征
        _stagger_sleep(patrol.settings)
        account_id: int = cast(int, account["id"])
        email: str = cast(str, account["email"])
        started_at: str = _now_iso()
        result: dict[str, object] = try_refresh_provider_oauth_token(
            settings=patrol.settings,
            provider=cast(str, account["provider"]),
            client_id=cast(str, account["client_id"]),
            refresh_token=cast(str, account["refresh_token"]),
            proxy_url=cast(str, account.get("proxy_url", "")),
            account_id=account_id,
        )
        log_status: str = "success" if result["success"] else "failed"
        _insert_refresh_log(
            patrol.settings,
            account_id,
            email,
            log_status,
            str(result.get("message", "")),
            str(result.get("error_detail", "")),
            started_at=started_at,
            round_id=patrol.round_id or None,
        )
        index: int = progress.advance(bool(result["success"]))
        with patrol._lock:
            patrol.current = index
            patrol.email = email
            patrol.success = progress.success_count
            patrol.failed = progress.fail_count
        patrol.append_event(
            {
                "type": "progress",
                "current": index,
                "total": patrol.total,
                "account_id": account_id,
                "email": email,
                "success": result["success"],
                "message": result.get("message", ""),
            }
        )

    def _finish_with_error(self, patrol: _Patrol, total: int, error: BaseException) -> None:
        with patrol._lock:
            patrol.status = "error"
            patrol.error = str(error)
            patrol.finished_at = _now_iso()
        _finish_refresh_round(
            patrol.settings,
            patrol.round_id,
            total,
            patrol.success,
            patrol.failed,
        )
        patrol.append_event(
            {
                "type": "complete",
                "total": total,
                "success": patrol.success,
                "failed": patrol.failed,
                "error": str(error),
            }
        )

    def snapshot(self, user_id: int) -> PatrolSnapshot:
        patrol = self._patrols.get(user_id)
        if patrol is None:
            return PatrolSnapshot(
                status="idle",
                mode="",
                mode_label="",
                group_id=None,
                total=0,
                current=0,
                success=0,
                failed=0,
                email="",
                started_at=None,
                finished_at=None,
                error="",
            )
        return patrol.snapshot()

    def events_since(self, user_id: int, seq: int) -> list[tuple[int, dict[str, object]]]:
        patrol = self._patrols.get(user_id)
        if patrol is None:
            return []
        return patrol.events_since(seq)

    def pause(self, user_id: int) -> bool:
        patrol = self._patrols.get(user_id)
        if patrol is None or patrol.status in TERMINAL_STATES:
            return False
        with patrol._lock:
            if patrol.status not in ("running", "starting"):
                return False
            patrol.status = "paused"
        patrol._pause.set()
        return True

    def resume(self, user_id: int) -> bool:
        patrol = self._patrols.get(user_id)
        if patrol is None or patrol.status != "paused":
            return False
        with patrol._lock:
            if patrol.status != "paused":
                return False
            patrol.status = "running"
        patrol._pause.clear()
        return True

    def stop(self, user_id: int) -> bool:
        patrol = self._patrols.get(user_id)
        if patrol is None or patrol.status in TERMINAL_STATES:
            return False
        patrol._stop.set()
        patrol._pause.clear()  # 暂停中也能立即终止
        with patrol._lock:
            if patrol.status in ("running", "starting"):
                patrol.status = "stopping"
        return True


manager = PatrolManager()
