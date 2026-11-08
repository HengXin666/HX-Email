"""Listening side of the gateway: ingest and cursor pulls.

Every store publishes what it stored to the hub (``server/hub/bus.py``), which wakes
only the waiters whose scope the message falls in. Waiting itself lives in
``server/hub/consume.py`` as coroutines, so a long-poll or SSE stream holds no thread.
A missed wake never loses data: a waiter re-reads by cursor.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Mapping
from typing import Final

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.contract.event import event_view
from hx_email.server.hub.bus import BUS, Hit
from hx_email.server.router.envelope import (
    Envelope,
    EnvelopeError,
    InboundMessage,
    validate_inbound,
)
from hx_email.server.router.impl.reader import (
    COLUMNS,
    ReadPage,
    _row_to_envelope,
    peer_of,
    read_messages,
)
from hx_email.server.router.impl.store import StoreResult, store_inbound
from hx_email.server.router.providers.impl.qq_events import to_envelope

LOGGER: logging.Logger = logging.getLogger("hx_email.gateway.listen")
MAX_RECENT: Final[int] = 200


def page_dict(page: ReadPage, include_raw: bool = False) -> dict[str, object]:
    return {
        "messages": [event_view(item.to_dict(include_raw)) for item in page.messages],
        "next_cursor": page.next_cursor,
        "has_more": page.has_more,
        "gap": page.gap,
    }


# 监听靠 hub 按命中唤醒而不是轮询: 无人等待时没有任何定时器, 空闲 CPU 为零
def pull(
    settings: Settings,
    user_id: int,
    source: str,
    cursor: str,
    *,
    limit: int = 50,
    direction: str = "inbound",
    include_raw: bool = False,
) -> dict[str, object]:
    page: ReadPage = read_messages(
        settings,
        user_id,
        source,
        cursor,
        limit=limit,
        direction=direction,
        include_raw=include_raw,
    )
    return page_dict(page, include_raw)


def recent_messages(
    settings: Settings, instance_id: int, address: str, limit: int = 50
) -> list[Envelope]:
    """Newest ``limit`` messages of one session, oldest first, both chat_id formats."""
    size: int = max(1, min(limit, MAX_RECENT))
    # 带类型的完整地址只认自己; 不带类型的纯号 (老页面) 匹配该实例下任一类型的同号会话
    bare: bool = ":" not in address
    peer: str = address if bare else peer_of(address)
    pattern: str = f"%:{instance_id}:%:{address}" if bare else address
    with connect(settings) as connection:
        rows: list[sqlite3.Row] = connection.execute(
            f"SELECT {COLUMNS} FROM messaging_messages "
            "WHERE instance_id = ? AND (chat_id = ? OR chat_id = ? OR chat_id LIKE ?) "
            "ORDER BY id DESC LIMIT ?",
            (instance_id, address, peer, pattern, size),
        ).fetchall()
    return [_row_to_envelope(settings, row, False) for row in reversed(rows)]


def store_envelopes(
    settings: Settings, instance_id: int, envelopes: list[dict[str, object]]
) -> int:
    """Validate and store provider envelopes; returns how many rows were new."""
    stored: int = 0
    hits: list[Hit] = []
    for envelope in envelopes:
        try:
            message: InboundMessage = validate_inbound(envelope, instance_id)
            result: StoreResult = store_inbound(settings, message)
        except (EnvelopeError, ValueError, OSError) as error:
            LOGGER.warning("dropped inbound envelope for instance %s: %s", instance_id, error)
            continue
        if result.stored or result.updated:
            stored += 1
            hits.append(Hit(instance_id, message.session.address, message.direction))
    BUS.publish(hits)
    return stored


def ingest_qq_event(settings: Settings, instance_id: int, payload: Mapping[str, object]) -> bool:
    """One OneBot event into the shared table; a redelivered event lands only once."""
    envelope: dict[str, object] | None = to_envelope(instance_id, payload)
    if envelope is None:
        return False
    return store_envelopes(settings, instance_id, [envelope]) > 0
