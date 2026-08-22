"""持久化巡检路由: 启动/状态/事件流/暂停/恢复/终止。

与旧版同步 SSE 端点 (refresh-all 等) 并存; 本组端点驱动 PatrolManager,
巡检在后台线程执行, 页面刷新或切换后仍可查询状态或重新订阅事件流。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from hx_email.api.dependencies import require_user
from hx_email.config import Settings
from hx_email.server.mail.impl.patrol.patrol_manager import (
    PatrolSnapshot,
    manager,
)
from hx_email.server.mail.impl.refresh_service import sse_event


class PatrolStartRequest(BaseModel):
    mode: str
    group_id: int | None = None
    account_ids: list[int] | None = None


async def patrol_event_stream(user_id: int) -> AsyncGenerator[str, None]:
    """SSE 事件流: 回放缓冲事件 (断线重连补全), 新事件实时推送, 终态后关闭。"""
    seq = 0
    sent_complete = False
    while True:
        snapshot: PatrolSnapshot = manager.snapshot(user_id)
        if snapshot.status == "idle":
            yield sse_event("status", snapshot.as_dict())
            return
        # 每轮先推送当前快照, 保证重连客户端立即获得最新进度
        yield sse_event("status", snapshot.as_dict())
        for event_seq, event in manager.events_since(user_id, seq):
            seq = event_seq
            event_type: str = str(event.get("type", "progress"))
            yield sse_event(event_type, event)
            if event_type == "complete":
                sent_complete = True
        if sent_complete:
            await asyncio.sleep(1.0)  # 短暂驻留确保 complete 送达
            return
        await asyncio.sleep(0.8)


def register_patrol_routes(router: APIRouter, settings: Settings) -> None:
    @router.post("/email-accounts/patrol/start")
    def patrol_start(
        payload: PatrolStartRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """启动巡检 (all/failed/group/ungrouped/selected); 已有任务进行中返回 409。"""
        user = require_user(settings, authorization)
        if payload.mode not in ("all", "failed", "group", "ungrouped", "selected"):
            raise HTTPException(status_code=422, detail="unsupported patrol mode")
        if payload.mode == "group" and payload.group_id is None:
            raise HTTPException(status_code=422, detail="group mode requires group_id")
        if payload.mode == "selected" and not payload.account_ids:
            raise HTTPException(status_code=422, detail="selected mode requires account_ids")
        started = manager.start(
            settings,
            user.id,
            payload.mode,
            group_id=payload.group_id,
            account_ids=payload.account_ids,
        )
        if not started:
            snapshot = manager.snapshot(user.id)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"已有巡检任务进行中 ({snapshot.mode_label}), 请先等待完成或终止",
            )
        return {"success": True, "snapshot": manager.snapshot(user.id).as_dict()}

    @router.get("/email-accounts/patrol/status")
    def patrol_status(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        return manager.snapshot(user.id).as_dict()

    @router.get("/email-accounts/patrol/stream")
    def patrol_stream(
        authorization: Annotated[str | None, Header()] = None,
    ) -> StreamingResponse:
        user = require_user(settings, authorization)
        return StreamingResponse(
            patrol_event_stream(user.id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/email-accounts/patrol/pause")
    def patrol_pause(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        paused = manager.pause(user.id)
        return {"success": paused, "snapshot": manager.snapshot(user.id).as_dict()}

    @router.post("/email-accounts/patrol/resume")
    def patrol_resume(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        resumed = manager.resume(user.id)
        return {"success": resumed, "snapshot": manager.snapshot(user.id).as_dict()}

    @router.post("/email-accounts/patrol/stop")
    def patrol_stop(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        stopped = manager.stop(user.id)
        return {"success": stopped, "snapshot": manager.snapshot(user.id).as_dict()}
