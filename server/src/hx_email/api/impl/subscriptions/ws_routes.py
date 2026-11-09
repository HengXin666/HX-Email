"""WebSocket face of a subscription: ``/api/v1/router/subscriptions/{id}/ws``.

Same feed as the SSE stream (``server/hub/consume.iterate_source``), plus a return
channel: the client acks over the socket instead of a separate POST. Browsers cannot
set ``Authorization`` on a WebSocket, so the token may also ride as a subprotocol
``bearer.<token>`` next to ``hx-router``; the server answers with ``hx-router``.

Server frames: ``ready``, ``messages`` (``messages`` plus ``next_cursor``),
``heartbeat`` (every 25 s idle), ``acked``, ``pong``, ``error``.
Client frames: ``{"type": "ack", "cursor": ...}`` and ``{"type": "ping"}``.
Close codes: 4401 unauthorized, 4404 subscription not found, 4409 paused.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Coroutine
from typing import Final

import anyio
import anyio.abc
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from hx_email.api.impl.gateway.auth import caller_user_id
from hx_email.config import Settings
from hx_email.server.hub.consume import Batch, route_batches
from hx_email.server.hub.route_model import Route
from hx_email.server.hub.subscriptions import ack_route, get_route
from hx_email.server.router.errors import RouterError

WS_PROTOCOL: Final[str] = "hx-router"
TOKEN_PROTOCOL_PREFIX: Final[str] = "bearer."


def credentials_of(websocket: WebSocket) -> tuple[str, str | None]:
    """``Authorization`` header first, then a ``bearer.<token>`` subprotocol."""
    offered: list[str] = [
        part.strip()
        for part in websocket.headers.get("sec-websocket-protocol", "").split(",")
        if part.strip()
    ]
    chosen: str | None = WS_PROTOCOL if WS_PROTOCOL in offered else None
    header: str = websocket.headers.get("authorization", "")
    if header:
        return header, chosen
    for part in offered:
        if part.startswith(TOKEN_PROTOCOL_PREFIX):
            return "Bearer " + part.removeprefix(TOKEN_PROTOCOL_PREFIX), chosen
    return "", chosen


class Channel:
    """Serialises sends: the feed and the ack replies share one socket."""

    def __init__(self, websocket: WebSocket) -> None:
        self.websocket: WebSocket = websocket
        self.lock: asyncio.Lock = asyncio.Lock()

    async def send(self, frame: dict[str, object]) -> None:
        async with self.lock:
            await self.websocket.send_json(frame)


async def pump(channel: Channel, batches: AsyncIterator[Batch]) -> None:
    async for batch in batches:
        if batch.messages:
            await channel.send(
                {"type": "messages", "messages": batch.messages, "next_cursor": batch.cursor}
            )
        else:
            await channel.send({"type": "heartbeat", "next_cursor": batch.cursor})


async def listen(channel: Channel, settings: Settings, user_id: int, route_id: int) -> None:
    while True:
        frame: object = await channel.websocket.receive_json()
        kind: str = str(frame.get("type") or "") if isinstance(frame, dict) else ""
        if kind == "ping":
            await channel.send({"type": "pong"})
            continue
        if kind != "ack" or not isinstance(frame, dict):
            await channel.send({"type": "error", "code": "bad_frame", "message": kind})
            continue
        try:
            route: dict[str, object] = await anyio.to_thread.run_sync(
                ack_route, settings, user_id, route_id, str(frame.get("cursor") or "")
            )
        except RouterError as error:
            await channel.send({"type": "error", **error.to_dict()})
            continue
        await channel.send({"type": "acked", "ack_cursor": route["ack_cursor"]})


async def first_done(group: anyio.abc.TaskGroup, work: Coroutine[object, object, None]) -> None:
    """Run one side of the socket; whichever side ends first stops the other."""
    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
        await work
    group.cancel_scope.cancel()


# WebSocket 与 SSE 共用 iterate_source; 浏览器无法设 Authorization, 令牌可走 bearer.<token> 子协议
# 决策记录: .agents/notes/implemented/feature/2026-11-08-router-push-transports.md
def register_subscription_ws(router: APIRouter, settings: Settings) -> None:
    @router.websocket("/router/subscriptions/{route_id}/ws")
    async def subscription_ws(
        websocket: WebSocket, route_id: int, cursor: str = "", auto_ack: bool = False
    ) -> None:
        authorization, chosen = credentials_of(websocket)
        try:
            user_id: int = await anyio.to_thread.run_sync(
                caller_user_id, settings, authorization or None
            )
            route: Route = await anyio.to_thread.run_sync(get_route, settings, user_id, route_id)
        except HTTPException:
            await websocket.close(code=4401, reason="unauthorized")
            return
        except RouterError as error:
            await websocket.close(code=4404, reason=error.code)
            return
        if route.status != "active":
            await websocket.close(code=4409, reason="paused")
            return
        await websocket.accept(subprotocol=chosen)
        channel = Channel(websocket)
        start: str = cursor or route.cursor()
        await channel.send(
            {
                "type": "ready",
                "subscription_id": route.id,
                "cursor": start,
                "ack_cursor": route.cursor(),
            }
        )
        # 用 anyio 任务组, 不用裸 asyncio.wait/gather: 收尾靠 anyio 取消作用域,
        # 混用时对端关闭与作用域取消赛跑, CancelledError 会漏出作用域
        async with anyio.create_task_group() as group:
            feed: AsyncIterator[Batch] = route_batches(settings, user_id, route, start, auto_ack)
            group.start_soon(first_done, group, pump(channel, feed))
            group.start_soon(first_done, group, listen(channel, settings, user_id, route.id))
