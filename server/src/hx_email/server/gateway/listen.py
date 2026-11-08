"""Listening side of the gateway: ingest, cursor pulls, long-poll waits.

Waiting is event-driven: every store calls ``SIGNAL.notify()``, and a waiter sleeps on
one ``threading.Condition`` until either that bump or its timeout. No timer runs while
nobody is waiting, and an idle gateway costs zero CPU, which is the A2 requirement of
ADR 0005. A missed notification never loses data: the waiter re-reads by cursor.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from collections.abc import Mapping
from typing import Final

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.contract.event import event_view
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
MAX_WAIT_SECONDS: Final[float] = 55.0
MAX_RECENT: Final[int] = 200


class MessageSignal:
    """A version counter plus a condition; ``wait`` returns early once it moves."""

    def __init__(self) -> None:
        self.condition: threading.Condition = threading.Condition()
        self.version: int = 0

    def notify(self) -> None:
        with self.condition:
            self.version += 1
            self.condition.notify_all()

    def wait(self, since: int, timeout: float) -> int:
        with self.condition:
            if self.version == since:
                self.condition.wait(timeout=max(0.0, timeout))
            return self.version


SIGNAL: MessageSignal = MessageSignal()


def page_dict(page: ReadPage, include_raw: bool = False) -> dict[str, object]:
    return {
        "messages": [event_view(item.to_dict(include_raw)) for item in page.messages],
        "next_cursor": page.next_cursor,
        "has_more": page.has_more,
        "gap": page.gap,
    }


# 监听靠条件变量唤醒而不是轮询: 无人等待时没有任何定时器, 空闲 CPU 为零
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


def wait_messages(
    settings: Settings,
    user_id: int,
    source: str,
    cursor: str,
    *,
    timeout_seconds: float = 25.0,
    limit: int = 20,
    direction: str = "inbound",
) -> dict[str, object]:
    """Block until ``source`` has messages after ``cursor`` or the timeout passes."""
    deadline: float = time.monotonic() + min(max(timeout_seconds, 0.0), MAX_WAIT_SECONDS)
    while True:
        version: int = SIGNAL.version
        page: ReadPage = read_messages(
            settings, user_id, source, cursor, limit=limit, direction=direction
        )
        remaining: float = deadline - time.monotonic()
        if page.messages or remaining <= 0:
            result: dict[str, object] = page_dict(page)
            result["timed_out"] = not page.messages
            return result
        SIGNAL.wait(version, remaining)


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
    for envelope in envelopes:
        try:
            message: InboundMessage = validate_inbound(envelope, instance_id)
            result: StoreResult = store_inbound(settings, message)
        except (EnvelopeError, ValueError, OSError) as error:
            LOGGER.warning("dropped inbound envelope for instance %s: %s", instance_id, error)
            continue
        stored += 1 if result.stored or result.updated else 0
    if stored:
        SIGNAL.notify()
    return stored


def ingest_qq_event(settings: Settings, instance_id: int, payload: Mapping[str, object]) -> bool:
    """One OneBot event into the shared table; a redelivered event lands only once."""
    envelope: dict[str, object] | None = to_envelope(instance_id, payload)
    if envelope is None:
        return False
    return store_envelopes(settings, instance_id, [envelope]) > 0
