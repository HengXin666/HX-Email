"""持久化巡检管理器 (per-user 全局单例)。

批量 Token 刷新在后台线程中执行, 与 HTTP 连接解耦:
- 页面刷新/切换后巡检继续运行, 新页面可随时查询状态或重新订阅事件流
- 支持暂停 / 恢复 / 终止
- 事件带自增序号缓冲在内存, 断线重连时可回放补全进度

状态模型见 patrol_state.py; 与 refresh_service 的同步 SSE 生成器并存,
后者保留给旧端点与外部同步调用 (均有测试覆盖)。
"""

from __future__ import annotations

import threading
import time
from typing import cast

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail.impl.oauth_tool import try_refresh_provider_oauth_token
from hx_email.server.mail.impl.patrol.patrol_state import (
    MODE_LABELS,
    TERMINAL_STATES,
    PatrolSnapshot,
    _Patrol,
)
from hx_email.server.mail.impl.refresh_log_service import (
    insert_refresh_log as _insert_refresh_log,
)
from hx_email.server.mail.impl.refresh_log_service import now_iso as _now_iso

__all__ = ["PatrolSnapshot", "manager"]


def _fetch_accounts(
    settings: Settings,
    user_id: int,
    mode: str,
    group_id: int | None = None,
    account_ids: list[int] | None = None,
) -> list[dict[str, object]]:
    """按目标拉取活跃 OAuth 账号列表 (含分组代理), 供巡检线程处理。"""
    base_select: str = (
        "SELECT ea.id, ea.primary_address, ea.provider, ea.client_id,"
        " ea.refresh_token, COALESCE(g.proxy_url, '') AS proxy_url"
        " FROM email_accounts ea LEFT JOIN groups g ON g.id = ea.group_id"
    )
    where: list[str] = [
        "ea.status = 'active'",
        "ea.user_id = ?",
        "ea.provider IN ('outlook', 'gmail')",
        "ea.refresh_token != ''",
    ]
    params: list[object] = [user_id]
    if mode == "failed":
        where.append(
            "ea.id IN ("
            " SELECT latest.account_id FROM ("
            "  SELECT account_id, MAX(id) AS max_id FROM refresh_logs GROUP BY account_id"
            " ) latest INNER JOIN refresh_logs rl ON rl.id = latest.max_id"
            " WHERE rl.status = 'failed'"
            ")"
        )
    elif mode == "group":
        where.append("ea.group_id = ?")
        params.append(group_id)
    elif mode == "ungrouped":
        where.append("ea.group_id IS NULL")
    elif mode == "selected":
        if not account_ids:
            return []
        placeholders = ",".join("?" for _ in account_ids)
        where.append(f"ea.id IN ({placeholders})")
        params.extend(account_ids)
    sql: str = f"{base_select} WHERE {' AND '.join(where)} ORDER BY ea.id"
    with connect(settings) as connection:
        rows = connection.execute(sql, params).fetchall()
    return [
        {
            "id": row["id"],
            "email": row["primary_address"],
            "provider": row["provider"],
            "client_id": row["client_id"],
            "refresh_token": row["refresh_token"],
            "proxy_url": row["proxy_url"] or "",
        }
        for row in rows
    ]


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
        patrol.append_event({"type": "start", "total": len(accounts)})
        patrol._thread = threading.Thread(
            target=self._run, args=(patrol, accounts), daemon=True, name=f"patrol-{user_id}"
        )
        patrol._thread.start()
        return True

    def _run(self, patrol: _Patrol, accounts: list[dict[str, object]]) -> None:
        total: int = len(accounts)
        try:
            for index, account in enumerate(accounts):
                if patrol._stop.is_set():
                    break
                # 暂停等待 (暂停期间停止信号可打断)
                while patrol._pause.is_set() and not patrol._stop.is_set():
                    time.sleep(0.3)
                if patrol._stop.is_set():
                    break
                account_id: int = cast(int, account["id"])
                email: str = cast(str, account["email"])
                started_at: str = _now_iso()
                result: dict[str, object] = try_refresh_provider_oauth_token(
                    settings=patrol.settings,
                    provider=cast(str, account["provider"]),
                    client_id=cast(str, account["client_id"]),
                    refresh_token=cast(str, account["refresh_token"]),
                    proxy_url=cast(str, account.get("proxy_url", "")),
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
                )
                with patrol._lock:
                    patrol.current = index + 1
                    patrol.email = email
                    if result["success"]:
                        patrol.success += 1
                    else:
                        patrol.failed += 1
                patrol.append_event(
                    {
                        "type": "progress",
                        "current": index + 1,
                        "total": total,
                        "account_id": account_id,
                        "email": email,
                        "success": result["success"],
                        "message": result.get("message", ""),
                    }
                )
            stopped: bool = patrol._stop.is_set()
            with patrol._lock:
                patrol.status = "stopped" if stopped else "done"
                patrol.finished_at = _now_iso()
            patrol.append_event(
                {
                    "type": "complete",
                    "total": total,
                    "success": patrol.success,
                    "failed": patrol.failed,
                    "stopped": stopped,
                }
            )
        except Exception as error:  # 巡检兜底, 状态写入快照
            with patrol._lock:
                patrol.status = "error"
                patrol.error = str(error)
                patrol.finished_at = _now_iso()
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
