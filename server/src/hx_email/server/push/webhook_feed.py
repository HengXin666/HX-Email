"""Webhook feeder: turns new messages in a subscription's scope into queued batches.

One daemon thread. It registers one hub waiter per active webhook subscription, built
from that subscription's own scope, so a message wakes the feeder only for the
subscriptions it falls in (no polling, no timer while idle). For each woken
subscription it reads from ``push_cursor`` by cursor, keeps what the filter accepts,
queues batches of at most 50 as ``router_outbox`` rows of ``kind='webhook'`` and moves
``push_cursor`` past them. Delivery itself is the dispatcher's job (``webhook_deliver``);
``ack_cursor`` only moves when the receiver answers 2xx.
"""

from __future__ import annotations

import logging
import threading
from typing import Final

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.contract.event import event_view
from hx_email.server.gateway.impl.dispatch import DISPATCHER
from hx_email.server.hub.bus import BUS, Waiter, matcher_for
from hx_email.server.hub.route_model import Route
from hx_email.server.hub.subscriptions import advance, load_route, webhook_routes
from hx_email.server.router.cursor import decode_cursor
from hx_email.server.router.impl.outbox import enqueue_webhook
from hx_email.server.router.impl.reader import ReadPage, owned_instances, read_messages

LOGGER: logging.Logger = logging.getLogger("hx_email.push.feed")
BATCH_SIZE: Final[int] = 50
PAGES_PER_ROUND: Final[int] = 20


def pending_batches(settings: Settings, route_id: int) -> int:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS n FROM router_outbox WHERE kind = 'webhook' AND route_id = ? "
            "AND status IN ('queued', 'sending', 'held')",
            (route_id,),
        ).fetchone()
    return int(row["n"]) if row is not None else 0


def message_id(view: dict[str, object]) -> int:
    text: str = str(view.get("id") or "m_0")
    return int(text.removeprefix("m_") or 0)


# 每个 webhook 订阅按自己的范围注册一个 hub 等待者, 只在命中时读库排批, push_cursor 与 ack 分开走
def feed_route(settings: Settings, route: Route) -> int:
    """Queue every accepted message after ``push_cursor``; returns batches queued."""
    if route.delivery != "webhook" or route.status != "active" or route.target is None:
        return 0
    queued: int = 0
    position: str = route.cursor(route.push_position)
    for _ in range(PAGES_PER_ROUND):
        page: ReadPage = read_messages(
            settings,
            route.user_id,
            route.source,
            position,
            limit=BATCH_SIZE,
            direction=route.filter.direction,
        )
        views: list[dict[str, object]] = [event_view(item.to_dict()) for item in page.messages]
        accepted: list[dict[str, object]] = [view for view in views if route.filter.accepts(view)]
        position = page.next_cursor
        if accepted:
            payload: dict[str, object] = {
                "type": "messages",
                "subscription_id": route.id,
                "messages": accepted,
                "next_cursor": position,
                "gap": page.gap,
            }
            enqueue_webhook(
                settings,
                route.user_id,
                route.id,
                payload,
                message_id(accepted[0]),
                message_id(accepted[-1]),
            )
            queued += 1
        stored: int = decode_cursor(position).position
        advance(settings, route.id, "push_cursor", stored)
        if not accepted and page.messages and pending_batches(settings, route.id) == 0:
            # 整页被过滤掉且没有在途批次: 没东西要投, ack 跟着前移, 积压不会虚高
            advance(settings, route.id, "ack_cursor", stored)
        if not page.has_more:
            break
    if queued:
        DISPATCHER.wake(settings)
    return queued


class WebhookFeeder:
    """Owns the per-subscription waiters and the thread that drains woken routes."""

    def __init__(self) -> None:
        self.lock: threading.Lock = threading.Lock()
        self.wake_event: threading.Event = threading.Event()
        self.dirty: set[int] = set()
        self.waiters: dict[int, Waiter] = {}
        self.thread: threading.Thread | None = None
        self.settings: Settings | None = None

    def start(self, settings: Settings) -> None:
        """Watch every active webhook subscription and catch up from ``push_cursor``."""
        self.settings = settings
        with self.lock:
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self.run, name="router-push", daemon=True)
                self.thread.start()
        self.reload(settings)

    def reload(self, settings: Settings) -> None:
        """Rebuild waiters after any subscription change; every webhook route is re-fed."""
        self.settings = settings
        routes: list[Route] = webhook_routes(settings)
        with connect(settings) as connection:
            owned: dict[int, list[int]] = {
                user: owned_instances(connection, user) for user in {r.user_id for r in routes}
            }
        with self.lock:
            for waiter in self.waiters.values():
                BUS.unregister(waiter)
            self.waiters = {}
            for route in routes:
                matcher = matcher_for(route.scope, owned[route.user_id], route.filter.direction)
                waiter = Waiter(matcher, MarkDirty(self, route.id))
                self.waiters[route.id] = BUS.register(waiter)
            self.dirty.update(self.waiters)
        self.wake_event.set()

    def mark(self, route_id: int) -> None:
        with self.lock:
            self.dirty.add(route_id)
        self.wake_event.set()

    def watching(self) -> int:
        with self.lock:
            return len(self.waiters)

    def run(self) -> None:
        while True:
            self.wake_event.wait()
            self.wake_event.clear()
            self.drain()

    def drain(self) -> int:
        """Feed every dirty route once; safe to call directly (tests)."""
        settings: Settings | None = self.settings
        with self.lock:
            batch: list[int] = sorted(self.dirty)
            self.dirty.clear()
        if settings is None:
            return 0
        queued: int = 0
        for route_id in batch:
            try:
                route: Route | None = load_route(settings, route_id)
                if route is not None:
                    queued += feed_route(settings, route)
            except Exception:  # one broken subscription must not stop the others
                LOGGER.exception("webhook feed failed for subscription %s", route_id)
        return queued


class MarkDirty:
    """Waiter callback: remember the route and poke the feeder thread (any thread)."""

    def __init__(self, feeder: WebhookFeeder, route_id: int) -> None:
        self.feeder: WebhookFeeder = feeder
        self.route_id: int = route_id

    def __call__(self) -> None:
        self.feeder.mark(self.route_id)


FEEDER: WebhookFeeder = WebhookFeeder()
