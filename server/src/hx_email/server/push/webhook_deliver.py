"""Webhook delivery: POST one queued batch, sign it, and walk the retry ladder.

The dispatcher claims ``kind='webhook'`` rows (one in flight per subscription, so a
receiver sees batches in order) and hands each to :func:`submit`, which runs the POST
on a small pool so a slow receiver never stalls platform sends. A 2xx retires the row
as ``sent`` and moves the subscription's ack to the batch's ``next_cursor``. Anything
else backs off from 10 s, doubling up to 1 hour with 20 percent jitter, until
``give_up_at`` (24 hours) turns the batch ``dead`` (spec 7.4). A paused subscription
parks its due batches as ``held``; resuming queues them again.
"""

from __future__ import annotations

import json
import logging
import random
import sqlite3
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Final

import requests

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.hub.route_model import Route
from hx_email.server.hub.subscriptions import advance, get_route, load_route
from hx_email.server.push.webhook_target import (
    DELIVERY_HEADER,
    SIGNATURE_HEADER,
    SUBSCRIPTION_HEADER,
    WebhookTarget,
    sign,
)
from hx_email.server.router.cursor import decode_cursor
from hx_email.server.router.errors import CursorInvalidError, RouteInvalidError
from hx_email.server.router.impl.outbox import Entry

LOGGER: logging.Logger = logging.getLogger("hx_email.push.deliver")
STAMP: Final[str] = "%Y-%m-%d %H:%M:%S"
TIMEOUT_SECONDS: Final[float] = 10.0
BACKOFF_START_SECONDS: Final[float] = 10.0
BACKOFF_CAP_SECONDS: Final[float] = 3600.0
GIVE_UP_HOURS: Final[int] = 24
POOL_SIZE: Final[int] = 4
DELIVERY_COLUMNS: Final[str] = (
    "id, status, attempts, idempotency_key, next_attempt_at, last_error, payload_json, "
    "created_at, updated_at"
)
Poster = Callable[[str, bytes, dict[str, str]], int]


def http_post(url: str, body: bytes, headers: dict[str, str]) -> int:
    reply = requests.post(
        url, data=body, headers=headers, timeout=TIMEOUT_SECONDS, allow_redirects=False
    )
    return int(reply.status_code)


def stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime(STAMP)


def headers_for(
    target: WebhookTarget, route_id: int, delivery_id: str, body: bytes
) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "User-Agent": "HX-Router-Webhook/1",
        SIGNATURE_HEADER: sign(target.secret, body),
        DELIVERY_HEADER: delivery_id,
        SUBSCRIPTION_HEADER: str(route_id),
    }


def set_row(settings: Settings, row_id: int, status: str, error: str = "", **extra: str) -> None:
    columns: str = "".join(f", {name} = ?" for name in extra)
    with connect(settings) as connection:
        connection.execute(
            f"UPDATE router_outbox SET status = ?, last_error = ?{columns}, "
            "updated_at = datetime('now') WHERE id = ?",
            (status, error[:1000], *extra.values(), row_id),
        )
        connection.commit()


def backoff_seconds(attempt: int, generator: random.Random) -> float:
    base: float = min(BACKOFF_CAP_SECONDS, BACKOFF_START_SECONDS * (2 ** max(0, attempt - 1)))
    return base * generator.uniform(0.8, 1.2)


def retry_or_dead(
    settings: Settings, entry: Entry, error: str, now: datetime, generator: random.Random
) -> str:
    """Schedule the next attempt, or retire the batch once ``give_up_at`` would pass."""
    due: datetime = now + timedelta(seconds=backoff_seconds(entry.attempts, generator))
    give_up: datetime = datetime.strptime(entry.give_up_at, STAMP).replace(tzinfo=UTC)
    if due >= give_up:
        set_row(settings, entry.id, "dead", error)
        return "dead"
    set_row(settings, entry.id, "queued", error, next_attempt_at=stamp(due))
    return "queued"


# webhook 投递: 2xx 才推进 ack; 失败 10 秒起翻倍到 1 小时, 24 小时后 dead; 暂停时置 held
# 决策记录: .agents/notes/implemented/feature/2026-11-08-router-push-transports.md
def deliver(
    settings: Settings,
    entry: Entry,
    *,
    post: Poster | None = None,
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> str:
    """POST one claimed batch and record the outcome; returns the row's new status."""
    route: Route | None = load_route(settings, entry.route_id or 0)
    if route is None or route.delivery != "webhook" or route.target is None:
        set_row(settings, entry.id, "failed", "route_gone: subscription is no longer a webhook")
        return "failed"
    if route.status != "active":
        set_row(settings, entry.id, "held", "subscription paused")
        return "held"
    body: bytes = entry.payload_json.encode("utf-8")
    sender: Poster = post or http_post
    error: str = ""
    try:
        code: int = sender(
            route.target.url, body, headers_for(route.target, route.id, entry.delivery_id, body)
        )
        if 200 <= code < 300:
            set_row(settings, entry.id, "sent")
            next_cursor: str = str(entry.payload.get("next_cursor") or "")
            if next_cursor:
                advance(settings, route.id, "ack_cursor", decode_cursor(next_cursor).position)
            return "sent"
        error = f"http_{code}"
    except (requests.RequestException, OSError, CursorInvalidError) as failure:
        error = f"{type(failure).__name__}: {failure}"
    LOGGER.info("webhook %s for subscription %s failed: %s", entry.delivery_id, route.id, error)
    return retry_or_dead(settings, entry, error, now or datetime.now(UTC), rng or random.Random())


POOL: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=POOL_SIZE, thread_name_prefix="webhook")


def submit(settings: Settings, entry: Entry, done: Callable[[], None]) -> None:
    """Deliver on the pool, then call ``done`` so the dispatcher can claim the next batch."""

    def job() -> None:
        try:
            deliver(settings, entry)
        except Exception:  # pragma: no cover - keep the row from sticking in sending
            LOGGER.exception("webhook delivery %s crashed", entry.delivery_id)
            set_row(settings, entry.id, "queued", "delivery crashed")
        finally:
            done()

    POOL.submit(job)


def ping(
    settings: Settings, user_id: int, route_id: int, post: Poster | None = None
) -> dict[str, object]:
    """Send a signed ``{"type": "ping"}`` right now so the user can check the receiver."""
    route: Route = get_route(settings, user_id, route_id)
    if route.target is None:
        raise RouteInvalidError("subscription has no webhook_url")
    body: bytes = json.dumps({"type": "ping", "subscription_id": route.id}).encode("utf-8")
    started: float = time.monotonic()
    try:
        code: int = (post or http_post)(
            route.target.url, body, headers_for(route.target, route.id, "ping", body)
        )
    except (requests.RequestException, OSError) as failure:
        return {"ok": False, "status_code": 0, "error": str(failure)[:300], "elapsed_ms": 0}
    elapsed: int = int((time.monotonic() - started) * 1000)
    return {"ok": 200 <= code < 300, "status_code": code, "error": "", "elapsed_ms": elapsed}


def delivery_dict(row: sqlite3.Row) -> dict[str, object]:
    try:
        payload: object = json.loads(str(row["payload_json"]))
    except ValueError:
        payload = {}
    messages: object = payload.get("messages") if isinstance(payload, dict) else None
    return {
        "delivery_id": f"d_{row['id']}",
        "status": str(row["status"]),
        "attempts": int(row["attempts"]),
        "range": str(row["idempotency_key"]),
        "messages": len(messages) if isinstance(messages, list) else 0,
        "next_attempt_at": str(row["next_attempt_at"] or ""),
        "last_error": str(row["last_error"] or ""),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


def list_deliveries(
    settings: Settings, user_id: int, route_id: int, limit: int = 20
) -> dict[str, object]:
    get_route(settings, user_id, route_id)
    with connect(settings) as connection:
        rows: list[sqlite3.Row] = connection.execute(
            f"SELECT {DELIVERY_COLUMNS} FROM router_outbox WHERE kind = 'webhook' "
            "AND route_id = ? ORDER BY id DESC LIMIT ?",
            (route_id, max(1, min(limit, 100))),
        ).fetchall()
    return {"subscription_id": route_id, "deliveries": [delivery_dict(row) for row in rows]}


def redeliver(
    settings: Settings, user_id: int, route_id: int, delivery_id: str
) -> dict[str, object]:
    """Queue a ``dead`` or ``failed`` batch again with a fresh 24 hour window."""
    get_route(settings, user_id, route_id)
    digits: str = delivery_id.removeprefix("d_")
    row_id: int = int(digits) if digits.isdigit() else 0
    moment: datetime = datetime.now(UTC)
    with connect(settings) as connection:
        changed = connection.execute(
            "UPDATE router_outbox SET status = 'queued', attempts = 0, next_attempt_at = ?, "
            "give_up_at = ?, last_error = '', updated_at = datetime('now') "
            "WHERE id = ? AND kind = 'webhook' AND route_id = ? AND status IN ('dead', 'failed')",
            (stamp(moment), stamp(moment + timedelta(hours=GIVE_UP_HOURS)), row_id, route_id),
        )
        connection.commit()
    if changed.rowcount != 1:
        raise RouteInvalidError(f"{delivery_id} is not a dead or failed batch of this subscription")
    return {"delivery_id": delivery_id, "status": "queued"}
