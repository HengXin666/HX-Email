"""Outbound dispatcher: the only code that turns an outbox row into a platform call.

One daemon thread, started on the first enqueue. Between rows it sleeps on an
``Event`` until the next row is due (``MIN(next_attempt_at)``) or a new enqueue wakes
it; with an empty queue it waits with no timeout, so an idle router has no timer at
all. A single thread also serialises every send of every account, which is exactly
what the per-account shaper assumes.

Per row: breaker -> shaper -> human-like jitter -> provider.send -> record the outcome.
A refused shaper decision is a rate-limit hold (``retry`` with ``retry_after``) that
does not burn an attempt; a risk-flagged failure feeds the breaker.
"""

from __future__ import annotations

import logging
import math
import sqlite3
import threading
import time
from datetime import UTC, datetime

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.gateway.impl.breaker import BREAKER
from hx_email.server.gateway.providers import (
    HUB,
    QZONE_TYPES,
    InstanceRow,
    load_instance,
    shaper_for,
)
from hx_email.server.hub.bus import BUS, Hit
from hx_email.server.push.webhook_deliver import submit
from hx_email.server.router.envelope import (
    InboundMessage,
    Sender,
    SessionAddress,
    parse_session,
)
from hx_email.server.router.impl.outbox import Entry, claim_due
from hx_email.server.router.impl.outbox_admin import get_entry, record_result
from hx_email.server.router.impl.shaper import Decision
from hx_email.server.router.impl.store import store_inbound
from hx_email.server.router.provider import (
    MessagingProvider,
    OutboundPayload,
    SendResult,
    SessionRef,
)
from hx_email.server.router.providers.qq import QQNapCatProvider

LOGGER: logging.Logger = logging.getLogger("hx_email.gateway.dispatch")
PENDING: tuple[str, ...] = ("queued", "sending")
CLAIM_BATCH: int = 10
STAMP: str = "%Y-%m-%d %H:%M:%S"


def mark(settings: Settings, delivery_id: int, status: str, error: str) -> None:
    with connect(settings) as connection:
        connection.execute(
            "UPDATE router_outbox SET status = ?, last_error = ?, updated_at = datetime('now') "
            "WHERE id = ?",
            (status, error[:1000], delivery_id),
        )
        connection.commit()


# 单个守护线程串行投递: 队列空时无超时等待, 有排队行只睡到最早 next_attempt_at, 空闲零 CPU
# 决策记录: .agents/notes/implemented/feature/2026-11-06-router-gateway-facade.md
def seconds_until_next(settings: Settings) -> float | None:
    with connect(settings) as connection:
        row: sqlite3.Row | None = connection.execute(
            "SELECT MIN(next_attempt_at) AS due FROM router_outbox AS o "
            "WHERE status = 'queued' AND NOT (kind = 'webhook' AND EXISTS ("
            "SELECT 1 FROM router_outbox AS f WHERE f.kind = 'webhook' "
            "AND f.route_id = o.route_id AND f.status = 'sending'))"
        ).fetchone()
    if row is None or not row["due"]:
        return None
    due: datetime = datetime.strptime(str(row["due"]), STAMP).replace(tzinfo=UTC)
    return max(0.0, (due - datetime.now(UTC)).total_seconds())


def record_outbound(settings: Settings, entry: Entry, platform_message_id: str) -> None:
    """Make a sent message readable through the same cursor as inbound ones."""
    address: SessionAddress = parse_session(entry.session)
    message = InboundMessage(
        session=address,
        direction="outbound",
        sender=Sender(id="", name="", is_self=True),
        text=str(entry.payload.get("text") or ""),
        platform_message_id=platform_message_id,
        occurred_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        dedup_key=f"out:{entry.delivery_id}",
        reply_to=str(entry.payload.get("reply_to") or ""),
    )
    try:
        store_inbound(settings, message)
    except (ValueError, OSError) as error:
        LOGGER.warning("cannot record outbound %s: %s", entry.delivery_id, error)
        return
    BUS.publish([Hit(address.instance_id, address.address, "outbound")])


class Dispatcher:
    def __init__(self) -> None:
        self.wake_event: threading.Event = threading.Event()
        self.done: threading.Condition = threading.Condition()
        self.start_lock: threading.Lock = threading.Lock()
        self.thread: threading.Thread | None = None
        self.settings: Settings | None = None

    def wake(self, settings: Settings) -> None:
        self.settings = settings
        with self.start_lock:
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self.run, name="router-dispatch", daemon=True)
                self.thread.start()
        self.wake_event.set()

    def run(self) -> None:
        while True:
            self.wake_event.clear()
            settings: Settings | None = self.settings
            delay: float | None = None
            if settings is not None:
                try:
                    delay = self.drain_once(settings)
                except Exception:  # pragma: no cover - keep the thread alive
                    LOGGER.exception("router dispatch round failed")
                    delay = 5.0
            if delay is None or delay > 0:
                self.wake_event.wait(timeout=delay)

    def drain_once(self, settings: Settings) -> float | None:
        entries: list[Entry] = claim_due(settings, limit=CLAIM_BATCH)
        for entry in entries:
            if entry.kind == "send":
                self.process(settings, entry)
            else:
                # webhook 在小线程池里投递, 慢接收端不拖住平台出站; 投完再唤醒本线程领下一批
                submit(settings, entry, lambda: self.wake(settings))
                continue
            with self.done:
                self.done.notify_all()
        return 0.0 if entries else seconds_until_next(settings)

    def process(self, settings: Settings, entry: Entry) -> None:
        instance_id: int = entry.instance_id or 0
        instance: InstanceRow | None = load_instance(settings, instance_id)
        if instance is None:
            mark(settings, entry.id, "failed", "instance no longer exists")
            return
        if BREAKER.is_manual(instance_id):
            mark(settings, entry.id, "held", "outbound manual_hold")
            return
        text: str = str(entry.payload.get("text") or "")
        session_type: str = parse_session(entry.session).session_type
        if session_type in QZONE_TYPES:
            HUB.qzone_for(settings, instance)  # 首次使用时为该实例配置空间档
        decision: Decision = shaper_for(session_type).acquire(instance_id, entry.session, text)
        if not decision.allowed:
            wait: int = max(1, math.ceil(decision.wait_seconds))
            record_result(
                settings,
                entry.id,
                SendResult(
                    "retry", retryable=True, error_code="rate_limited", retry_after_seconds=wait
                ),
            )
            return
        if decision.jitter_seconds > 0:
            time.sleep(decision.jitter_seconds)
        result: SendResult = self.call_provider(settings, instance, entry, text)
        if result.risk_signal:
            BREAKER.record_risk(instance_id)
        if result.status == "failed":
            mark(settings, entry.id, "failed", f"{result.error_code}: {result.error_message}")
            return
        record_result(settings, entry.id, result)
        if result.status == "sent":
            record_outbound(settings, entry, result.platform_message_id)

    def call_provider(
        self, settings: Settings, instance: InstanceRow, entry: Entry, text: str
    ) -> SendResult:
        try:
            address: SessionAddress = parse_session(entry.session)
            provider: MessagingProvider = HUB.for_session(settings, instance, address.session_type)
            if (
                isinstance(provider, QQNapCatProvider)
                and entry.session not in provider.known_sessions
            ):
                provider.list_sessions(instance.id)
            ref = SessionRef(
                entry.session,
                address.platform,
                instance.id,
                address.session_type,
                address.peer,
                str(entry.payload.get("title") or ""),
            )
            payload = OutboundPayload(
                entry.delivery_id,
                text,
                str(entry.payload.get("reply_to") or ""),
                str(entry.payload.get("title") or ""),
            )
            return provider.send(ref, payload)
        except Exception as error:  # a provider bug must not kill the dispatcher
            LOGGER.warning("provider call failed for %s: %s", entry.delivery_id, error)
            return SendResult(
                "retry", retryable=True, error_code="provider_error", error_message=str(error)
            )

    def wait_for(self, settings: Settings, delivery_id: int, seconds: float) -> Entry | None:
        """Block until the row leaves queued/sending or ``seconds`` pass."""
        deadline: float = time.monotonic() + max(0.0, seconds)
        while True:
            entry: Entry | None = get_entry(settings, delivery_id)
            remaining: float = deadline - time.monotonic()
            if entry is None or entry.status not in PENDING or remaining <= 0:
                return entry
            with self.done:
                self.done.wait(timeout=min(remaining, 1.0))


DISPATCHER: Dispatcher = Dispatcher()
