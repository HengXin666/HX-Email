"""Outbound queue: idempotent enqueue, exclusive claim, retry accounting.

The outbox owns *queue* semantics only. It never performs a platform call: the drain
loop asks a provider to send and then reports the outcome back through
``record_result``. Keeping the two apart is what makes the retry matrix and the
idempotency window testable without a network.

Idempotency is enforced by the partial unique indexes in the migration:
``(instance_id, idempotency_key)`` for ``kind='send'`` and ``(route_id, idempotency_key)``
for ``kind='webhook'``, both retired by ``purge_terminal`` after the 7 day window.

Retry policy (spec 9.3): a ``retry`` result with ``retry_after_seconds`` set is a
*rate-limit hold*, not a failure, so it does not consume an attempt. Only genuine
failures walk the backoff ladder, and the fourth one retires the row.
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from hx_email.config import Settings
from hx_email.database import connect

MAX_ATTEMPTS: Final[int] = 4
BACKOFF_START_SECONDS: Final[float] = 2.0
BACKOFF_CAP_SECONDS: Final[float] = 900.0
IDEMPOTENCY_WINDOW_DAYS: Final[int] = 7
GIVE_UP_HOURS: Final[int] = 24
STAMP: Final[str] = "%Y-%m-%d %H:%M:%S"
FEEDBACK_KEY_MIN: Final[int] = 8
BASIS_POINTS: Final[int] = 100

TERMINAL_STATUSES: Final[tuple[str, ...]] = ("sent", "failed")


class OutboxConflictError(Exception):
    """A row exists with the same idempotency key but a different payload."""


@dataclass(frozen=True)
class Entry:
    """One queue row; ``delivery_id`` is what tools and providers exchange."""

    id: int
    kind: str
    instance_id: int | None
    route_id: int | None
    session: str
    payload_json: str
    idempotency_key: str
    status: str
    attempts: int
    next_attempt_at: str
    give_up_at: str
    platform_message_id: str
    last_error: str

    @property
    def delivery_id(self) -> str:
        return f"d_{self.id}"

    @property
    def payload(self) -> dict[str, object]:
        try:
            parsed: object = json.loads(self.payload_json)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}


@dataclass(frozen=True)
class EnqueueResult:
    """``deduplicated`` tells the caller it hit the idempotency window."""

    entry: Entry
    deduplicated: bool


_COLUMNS: Final[str] = (
    "id, kind, instance_id, route_id, session, payload_json, idempotency_key, status, "
    "attempts, next_attempt_at, give_up_at, platform_message_id, last_error"
)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime(STAMP)


def _row(row: sqlite3.Row) -> Entry:
    return Entry(
        id=int(row["id"]),
        kind=str(row["kind"]),
        instance_id=None if row["instance_id"] is None else int(row["instance_id"]),
        route_id=None if row["route_id"] is None else int(row["route_id"]),
        session=str(row["session"] or ""),
        payload_json=str(row["payload_json"]),
        idempotency_key=str(row["idempotency_key"]),
        status=str(row["status"]),
        attempts=int(row["attempts"]),
        next_attempt_at=str(row["next_attempt_at"] or ""),
        give_up_at=str(row["give_up_at"] or ""),
        platform_message_id=str(row["platform_message_id"] or ""),
        last_error=str(row["last_error"] or ""),
    )


def _dump(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _existing_send(
    connection: sqlite3.Connection, instance_id: int, key: str
) -> sqlite3.Row | None:
    row: sqlite3.Row | None = connection.execute(
        f"SELECT {_COLUMNS} FROM router_outbox "
        "WHERE kind = 'send' AND instance_id = ? AND idempotency_key = ?",
        (instance_id, key),
    ).fetchone()
    return row


def _existing_webhook(
    connection: sqlite3.Connection, route_id: int, key: str
) -> sqlite3.Row | None:
    row: sqlite3.Row | None = connection.execute(
        f"SELECT {_COLUMNS} FROM router_outbox "
        "WHERE kind = 'webhook' AND route_id = ? AND idempotency_key = ?",
        (route_id, key),
    ).fetchone()
    return row


# 路由层订阅与分发的决策记录, 实现规格见 docs/messaging-router.md
# .agents/notes/implemented/feature/2026-11-02-messaging-router-gateway.md
def enqueue_send(
    settings: Settings,
    user_id: int,
    instance_id: int,
    session: str,
    payload: dict[str, object],
    idempotency_key: str,
    *,
    held: bool = False,
    now: datetime | None = None,
) -> EnqueueResult:
    """Queue an outbound message; a repeated key returns the original row."""
    if len(idempotency_key) < FEEDBACK_KEY_MIN:
        raise ValueError(
            f"idempotency_key must be at least {FEEDBACK_KEY_MIN} characters, "
            f"got {len(idempotency_key)}"
        )
    body: str = _dump(payload)
    moment: datetime = now or datetime.now(UTC)
    with connect(settings) as connection:
        existing: sqlite3.Row | None = _existing_send(connection, instance_id, idempotency_key)
        if existing is not None:
            # A repeated key is the idempotency window doing its job: the caller gets
            # the original row back and nothing new is sent, whatever the new payload.
            return EnqueueResult(entry=_row(existing), deduplicated=True)
        cursor: sqlite3.Cursor = connection.execute(
            """
            INSERT INTO router_outbox (
                user_id, kind, instance_id, route_id, session, payload_json,
                idempotency_key, status, next_attempt_at, give_up_at
            ) VALUES (?, 'send', ?, NULL, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                instance_id,
                session,
                body,
                idempotency_key,
                "held" if held else "queued",
                _stamp(moment),
                _stamp(moment + timedelta(hours=GIVE_UP_HOURS)),
            ),
        )
        created: sqlite3.Row | None = _existing_send(connection, instance_id, idempotency_key)
        connection.commit()
    if created is None:  # pragma: no cover - insert just succeeded
        raise OutboxConflictError(f"row vanished after insert: {cursor.lastrowid}")
    return EnqueueResult(entry=_row(created), deduplicated=False)


def enqueue_webhook(
    settings: Settings,
    user_id: int,
    route_id: int,
    payload: dict[str, object],
    first_message_id: int,
    last_message_id: int,
    *,
    now: datetime | None = None,
) -> EnqueueResult:
    """Queue one webhook delivery covering the closed range of message ids."""
    key: str = f"m_{first_message_id}-m_{last_message_id}"
    body: str = _dump(payload)
    moment: datetime = now or datetime.now(UTC)
    with connect(settings) as connection:
        existing: sqlite3.Row | None = _existing_webhook(connection, route_id, key)
        if existing is not None:
            return EnqueueResult(entry=_row(existing), deduplicated=True)
        connection.execute(
            """
            INSERT INTO router_outbox (
                user_id, kind, instance_id, route_id, session, payload_json,
                idempotency_key, status, next_attempt_at, give_up_at
            ) VALUES (?, 'webhook', NULL, ?, '', ?, ?, 'queued', ?, ?)
            """,
            (
                user_id,
                route_id,
                body,
                key,
                _stamp(moment),
                _stamp(moment + timedelta(hours=GIVE_UP_HOURS)),
            ),
        )
        created: sqlite3.Row | None = _existing_webhook(connection, route_id, key)
        connection.commit()
    if created is None:  # pragma: no cover
        raise OutboxConflictError(f"webhook row vanished: {key}")
    return EnqueueResult(entry=_row(created), deduplicated=False)


def claim_due(settings: Settings, *, limit: int = 20, now: datetime | None = None) -> list[Entry]:
    """Claim due rows for sending, one webhook at a time per route.

    The ``status = 'queued'`` guard makes the claim exclusive across concurrent drain
    loops: the loser rewrites zero rows and gets nothing back. Webhooks are additionally
    serialised per route so an endpoint never receives two batches out of order.
    """
    moment: str = _stamp(now or datetime.now(UTC))
    claimed: list[Entry] = []
    with connect(settings) as connection:
        rows: list[sqlite3.Row] = connection.execute(
            f"SELECT {_COLUMNS} FROM router_outbox "
            "WHERE status = 'queued' AND next_attempt_at <= ? "
            "ORDER BY created_at ASC, id ASC LIMIT ?",
            (moment, limit),
        ).fetchall()
        expired: sqlite3.Cursor = connection.execute(
            "UPDATE router_outbox SET status = 'failed', last_error = 'give_up_at passed', "
            "updated_at = datetime('now') WHERE status = 'queued' AND give_up_at <= ?",
            (moment,),
        )
        del expired
        busy_routes: set[int] = set()
        for row in rows:
            route_id: int | None = None if row["route_id"] is None else int(row["route_id"])
            if route_id is not None:
                if route_id in busy_routes or _route_in_flight(connection, route_id):
                    continue
                busy_routes.add(route_id)
            changed: sqlite3.Cursor = connection.execute(
                "UPDATE router_outbox SET status = 'sending', attempts = attempts + 1, "
                "updated_at = datetime('now') WHERE id = ? AND status = 'queued'",
                (int(row["id"]),),
            )
            if changed.rowcount == 1:
                claimed.append(
                    dataclasses.replace(
                        _row(row), status="sending", attempts=int(row["attempts"]) + 1
                    )
                )
        connection.commit()
    return claimed


def _route_in_flight(connection: sqlite3.Connection, route_id: int) -> bool:
    row: sqlite3.Row | None = connection.execute(
        "SELECT 1 AS busy FROM router_outbox "
        "WHERE kind = 'webhook' AND route_id = ? AND status = 'sending' LIMIT 1",
        (route_id,),
    ).fetchone()
    return row is not None
