"""Async consumption: long-poll and SSE that hold no thread while they wait.

Each wait registers a hub waiter first, then reads by cursor in a short worker-thread
call (SQLite is sync), and only then sleeps on an ``asyncio.Event``. Registering before
the read closes the race where a message lands between "read found nothing" and
"start waiting". While a consumer sleeps it costs one coroutine and one set entry,
not a thread-pool slot, so a few hundred idle streams no longer starve the API.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from functools import partial
from typing import Final

import anyio

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.contract.event import event_view
from hx_email.server.hub.bus import BUS, Matcher, async_waiter, matcher_for
from hx_email.server.hub.route_model import Route
from hx_email.server.hub.subscriptions import ack_route, get_route
from hx_email.server.router.impl.reader import (
    ReadPage,
    Source,
    owned_instances,
    parse_source,
    read_messages,
)

MAX_WAIT_SECONDS: Final[float] = 55.0
HEARTBEAT_SECONDS: Final[float] = 25.0
Accept = Callable[[dict[str, object]], bool]


def accept_all(view: dict[str, object]) -> bool:
    return isinstance(view, dict)


def sse_frame(payload: dict[str, object], frame_id: str = "", event: str = "") -> str:
    head: str = f"id: {frame_id}\n" if frame_id else ""
    kind: str = f"event: {event}\n" if event else ""
    return f"{head}{kind}data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def owned_of(settings: Settings, user_id: int) -> list[int]:
    with connect(settings) as connection:
        return owned_instances(connection, user_id)


async def read_page(
    settings: Settings, user_id: int, source: str, cursor: str, limit: int, direction: str
) -> ReadPage:
    return await anyio.to_thread.run_sync(
        partial(read_messages, settings, user_id, source, cursor, limit=limit, direction=direction)
    )


# 先注册等待者再读库, 再睡在 asyncio.Event 上: 不漏唤醒, 等待期间不占线程池
# 决策记录: .agents/notes/implemented/feature/2026-11-08-router-hub-subscriptions.md
async def wait_source(
    settings: Settings,
    user_id: int,
    source: str,
    cursor: str,
    *,
    timeout_seconds: float = 25.0,
    limit: int = 20,
    direction: str = "inbound",
    accept: Accept = accept_all,
) -> dict[str, object]:
    """Return once ``source`` has accepted messages after ``cursor``, or on timeout."""
    deadline: float = time.monotonic() + min(max(timeout_seconds, 0.0), MAX_WAIT_SECONDS)
    scope: Source = parse_source(source)
    owned: list[int] = await anyio.to_thread.run_sync(owned_of, settings, user_id)
    matcher: Matcher = matcher_for(scope, owned, direction)
    position: str = cursor
    gap: bool = False
    while True:
        waiter, event = async_waiter(matcher)
        BUS.register(waiter)
        try:
            page: ReadPage = await read_page(settings, user_id, source, position, limit, direction)
            gap = gap or page.gap
            position = page.next_cursor
            views: list[dict[str, object]] = [event_view(item.to_dict()) for item in page.messages]
            accepted: list[dict[str, object]] = [view for view in views if accept(view)]
            remaining: float = deadline - time.monotonic()
            if accepted or remaining <= 0:
                return {
                    "messages": accepted,
                    "next_cursor": position,
                    "has_more": page.has_more,
                    "gap": gap,
                    "timed_out": not accepted,
                }
            if page.has_more or page.messages:
                continue  # 整页都被过滤掉了: 游标已前移, 不睡直接读下一页
            try:
                await asyncio.wait_for(event.wait(), timeout=remaining)
            except TimeoutError:
                continue
        finally:
            BUS.unregister(waiter)


async def wait_route(
    settings: Settings,
    user_id: int,
    route_id: int,
    *,
    cursor: str = "",
    timeout_seconds: float = 25.0,
    limit: int = 20,
) -> dict[str, object]:
    """Long-poll a subscription from ``cursor`` or its ack; does not move the ack."""
    route: Route = await anyio.to_thread.run_sync(get_route, settings, user_id, route_id)
    base: dict[str, object] = {"subscription_id": route.id, "ack_cursor": route.cursor()}
    if route.status != "active":
        return {
            **base,
            "messages": [],
            "next_cursor": cursor or route.cursor(),
            "has_more": False,
            "gap": False,
            "timed_out": True,
            "paused": True,
        }
    page: dict[str, object] = await wait_source(
        settings,
        user_id,
        route.source,
        cursor or route.cursor(),
        timeout_seconds=timeout_seconds,
        limit=limit,
        direction=route.filter.direction,
        accept=route.filter.accepts,
    )
    return {**base, **page}


@dataclass(frozen=True)
class Batch:
    """What one wake-up produced: accepted views (empty on a heartbeat) and the cursor."""

    messages: list[dict[str, object]]
    cursor: str


async def iterate_source(
    settings: Settings,
    user_id: int,
    source: str,
    start: str,
    *,
    direction: str = "inbound",
    accept: Accept = accept_all,
    ack_route_id: int = 0,
) -> AsyncIterator[Batch]:
    """Batches forever, one per wake-up or heartbeat; SSE and WebSocket share this loop."""
    position: str = start
    while True:
        page: dict[str, object] = await wait_source(
            settings,
            user_id,
            source,
            position,
            timeout_seconds=HEARTBEAT_SECONDS,
            direction=direction,
            accept=accept,
        )
        position = str(page["next_cursor"])
        items: object = page["messages"]
        accepted: list[dict[str, object]] = list(items) if isinstance(items, list) else []
        if accepted and ack_route_id:
            await anyio.to_thread.run_sync(ack_route, settings, user_id, ack_route_id, position)
        yield Batch(accepted, position)


async def stream_source(
    settings: Settings,
    user_id: int,
    source: str,
    start: str,
    *,
    direction: str = "inbound",
    accept: Accept = accept_all,
    ack_route_id: int = 0,
    ready: bool = False,
) -> AsyncIterator[str]:
    """SSE frames forever: one ``data`` frame per message, a comment as heartbeat."""
    if ready:
        yield sse_frame({"cursor": start}, event="ready")
    batches: AsyncIterator[Batch] = iterate_source(
        settings,
        user_id,
        source,
        start,
        direction=direction,
        accept=accept,
        ack_route_id=ack_route_id,
    )
    async for batch in batches:
        if not batch.messages:
            yield ":\n\n"
        for item in batch.messages:
            yield sse_frame(item, str(item.get("cursor", "")))


def route_stream(
    settings: Settings, user_id: int, route: Route, start: str, auto_ack: bool
) -> AsyncIterator[str]:
    """SSE on a subscription: resumes from ``start`` (Last-Event-ID) or the ack."""
    return stream_source(
        settings,
        user_id,
        route.source,
        start or route.cursor(),
        direction=route.filter.direction,
        accept=route.filter.accepts,
        ack_route_id=route.id if auto_ack else 0,
        ready=True,
    )


def route_batches(
    settings: Settings, user_id: int, route: Route, start: str, auto_ack: bool
) -> AsyncIterator[Batch]:
    """WebSocket feed on a subscription: same resume and filter rules as SSE."""
    return iterate_source(
        settings,
        user_id,
        route.source,
        start or route.cursor(),
        direction=route.filter.direction,
        accept=route.filter.accepts,
        ack_route_id=route.id if auto_ack else 0,
    )
