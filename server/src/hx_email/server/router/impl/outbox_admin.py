"""Outbox maintenance: lookup, holds, restart recovery and retention.

Split from :mod:`outbox` so each file stays inside the 300 line budget. The split is
along a real seam: ``outbox`` handles the send pipeline (enqueue, claim, record a
result), while this module handles the operator-facing surface (find a delivery, hold
an instance, reconcile after a crash, retire old rows).
"""

from __future__ import annotations

import random
import sqlite3
from datetime import UTC, datetime, timedelta

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.router.impl.outbox import (
    _COLUMNS,
    BACKOFF_CAP_SECONDS,
    BACKOFF_START_SECONDS,
    MAX_ATTEMPTS,
    TERMINAL_STATUSES,
    Entry,
    _existing_send,
    _row,
    _stamp,
)
from hx_email.server.router.provider import SendResult


def get_entry(settings: Settings, delivery_id: int) -> Entry | None:
    with connect(settings) as connection:
        row: sqlite3.Row | None = connection.execute(
            f"SELECT {_COLUMNS} FROM router_outbox WHERE id = ?",
            (delivery_id,),
        ).fetchone()
    return None if row is None else _row(row)


def find_send(settings: Settings, instance_id: int, idempotency_key: str) -> Entry | None:
    with connect(settings) as connection:
        row: sqlite3.Row | None = _existing_send(connection, instance_id, idempotency_key)
    return None if row is None else _row(row)


def set_instance_held(settings: Settings, instance_id: int, held: bool) -> int:
    """Hold or release every queued message of one instance; returns rows touched.

    Releasing only touches rows the hold put there, so a message queued while the
    instance was held is never silently resumed by an unrelated release.
    """
    with connect(settings) as connection:
        if held:
            changed: sqlite3.Cursor = connection.execute(
                "UPDATE router_outbox SET status = 'held', updated_at = datetime('now') "
                "WHERE kind = 'send' AND instance_id = ? AND status = 'queued'",
                (instance_id,),
            )
        else:
            changed = connection.execute(
                "UPDATE router_outbox SET status = 'queued', updated_at = datetime('now') "
                "WHERE kind = 'send' AND instance_id = ? AND status = 'held'",
                (instance_id,),
            )
        connection.commit()
    return changed.rowcount


def recover_after_restart(settings: Settings, *, now: datetime | None = None) -> tuple[int, int]:
    """Reconcile rows left in flight by a crash: (marked unknown, requeued webhooks).

    A send stuck in ``sending`` may have reached the platform, so it becomes
    ``unknown`` and waits for marker reconciliation rather than resending. Webhook
    deliveries are idempotent on the receiving side, so they simply go back to queued.
    """
    del now
    with connect(settings) as connection:
        marked: sqlite3.Cursor = connection.execute(
            "UPDATE router_outbox SET status = 'unknown', updated_at = datetime('now') "
            "WHERE kind = 'send' AND status = 'sending'"
        )
        requeued: sqlite3.Cursor = connection.execute(
            "UPDATE router_outbox SET status = 'queued', updated_at = datetime('now') "
            "WHERE kind = 'webhook' AND status = 'sending'"
        )
        connection.commit()
    return marked.rowcount, requeued.rowcount


def purge_terminal(settings: Settings, *, now: datetime | None = None) -> int:
    """Drop retired rows past their give-up date, ending the idempotency window."""
    moment: str = _stamp(now or datetime.now(UTC))
    with connect(settings) as connection:
        changed: sqlite3.Cursor = connection.execute(
            "DELETE FROM router_outbox WHERE status IN ('sent', 'failed', 'unknown', 'dead') "
            "AND give_up_at <= ?",
            (moment,),
        )
        connection.commit()
    return changed.rowcount


# 发送类 failed 直接终态不重试: 对风控中的个人号反复重发正是封号路径
# 决策记录: .agents/notes/implemented/feature/2026-11-06-router-gateway-facade.md
def record_result(
    settings: Settings,
    delivery_id: int,
    result: SendResult,
    *,
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> Entry:
    """Apply a provider outcome to a claimed row and return its new state.

    ``sent`` retires the row. ``unknown`` keeps it for reconciliation instead of
    resending, because the platform may already have the message. ``retry`` with
    ``retry_after_seconds`` is a rate-limit hold that does not burn an attempt.
    """
    moment: datetime = now or datetime.now(UTC)
    generator: random.Random = rng or random.Random()
    with connect(settings) as connection:
        row: sqlite3.Row | None = connection.execute(
            f"SELECT {_COLUMNS} FROM router_outbox WHERE id = ?",
            (delivery_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"no outbox row with id {delivery_id}")
        current: Entry = _row(row)
        if current.status in TERMINAL_STATUSES:
            raise ValueError(f"row {delivery_id} is already {current.status}")
        if result.status == "sent":
            _apply(
                connection, delivery_id, "sent", current.attempts, result.platform_message_id, ""
            )
        elif result.status == "unknown":
            _apply(connection, delivery_id, "unknown", current.attempts, "", result.error_message)
        elif result.status == "failed" and (
            current.kind == "send" or result.error_code == "route_gone"
        ):
            # A provider "failed" is terminal (risk control, muted, bad target): retrying
            # it is exactly the repeated hammering that gets a personal account banned.
            reason: str = result.error_message or result.error_code
            _apply(connection, delivery_id, "failed", current.attempts, "", reason)
        elif result.status == "retry" and result.retry_after_seconds:
            # A rate-limit hold is not a failure: refund the attempt charged at claim
            # time, so a long backoff never walks the row toward retirement.
            next_at: str = _stamp(moment + timedelta(seconds=result.retry_after_seconds))
            connection.execute(
                "UPDATE router_outbox SET status = 'queued', next_attempt_at = ?, "
                "attempts = MAX(0, attempts - 1), updated_at = datetime('now') "
                "WHERE id = ?",
                (next_at, delivery_id),
            )
        else:
            attempt: int = current.attempts
            if attempt >= MAX_ATTEMPTS:
                _apply(connection, delivery_id, "failed", attempt, "", result.error_message)
            else:
                delay: float = _backoff(attempt, generator)
                connection.execute(
                    "UPDATE router_outbox SET status = 'queued', attempts = ?, "
                    "last_error = ?, next_attempt_at = ?, updated_at = datetime('now') "
                    "WHERE id = ?",
                    (
                        attempt,
                        result.error_message[:1000],
                        _stamp(moment + timedelta(seconds=delay)),
                        delivery_id,
                    ),
                )
        refreshed: sqlite3.Row | None = connection.execute(
            f"SELECT {_COLUMNS} FROM router_outbox WHERE id = ?",
            (delivery_id,),
        ).fetchone()
        connection.commit()
    if refreshed is None:  # pragma: no cover
        raise ValueError(f"row {delivery_id} vanished")
    return _row(refreshed)


def _backoff(attempt: int, generator: random.Random) -> float:
    """Exponential backoff with +-20 percent jitter, capped."""
    base: float = min(BACKOFF_CAP_SECONDS, BACKOFF_START_SECONDS * (2 ** (attempt - 1)))
    spread: float = base * 0.2
    return max(0.0, base + generator.uniform(-spread, spread))


def _apply(
    connection: sqlite3.Connection,
    delivery_id: int,
    status: str,
    attempts: int,
    platform_message_id: str,
    error: str,
) -> None:
    connection.execute(
        "UPDATE router_outbox SET status = ?, attempts = ?, platform_message_id = ?, "
        "last_error = ?, updated_at = datetime('now') WHERE id = ?",
        (status, attempts, platform_message_id, error[:1000], delivery_id),
    )
