"""SQLite outbox operations for new-mail delivery."""

from __future__ import annotations

from collections.abc import Sequence
from sqlite3 import Row

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.notifications.models import (
    DeliveryChannel,
    DeliveryConfig,
    DeliveryJob,
    StoredMessageEvent,
)
from hx_email.server.settings_service import get_setting

MAX_DELIVERY_ATTEMPTS: int = 3


def _enabled(value: str) -> bool:
    return value.lower() == "true"


def _placeholders(values: Sequence[object]) -> str:
    return ",".join("?" for _value in values)


def _row_to_event(row: Row) -> StoredMessageEvent:
    return StoredMessageEvent(
        id=row["id"],
        user_id=row["user_id"],
        usable_email_id=row["usable_email_id"],
        email_account_id=row["email_account_id"],
        address=row["address"],
        group_id=row["group_id"],
        group_name=row["group_name"] or "",
        email_notify_enabled=bool(row["email_notify_enabled"]),
        group_notify_enabled=bool(row["group_notify_enabled"]),
        account_telegram_enabled=bool(row["account_telegram_enabled"]),
        from_address=row["from_address"],
        recipient_address=row["recipient_address"],
        subject=row["subject"],
        body=row["body"],
        received_at=row["received_at"] or row["created_at"],
    )


def load_delivery_config(settings: Settings) -> DeliveryConfig:
    return DeliveryConfig(
        email_enabled=_enabled(get_setting(settings, "email_notification_enabled", "false")),
        telegram_enabled=_enabled(get_setting(settings, "telegram_notification_enabled", "false")),
        webhook_enabled=_enabled(get_setting(settings, "webhook_notification_enabled", "false")),
        script_enabled=_enabled(get_setting(settings, "script_notification_enabled", "false")),
    )


def load_message_events(
    settings: Settings,
    message_ids: Sequence[int],
) -> list[StoredMessageEvent]:
    if not message_ids:
        return []
    placeholders: str = _placeholders(message_ids)
    with connect(settings) as connection:
        rows = connection.execute(
            f"""
            SELECT m.id, m.user_id, m.usable_email_id, m.email_account_id,
                   m.from_address, m.recipient_address, m.subject, m.body,
                   m.received_at, m.created_at, ue.address,
                   COALESCE(ue.group_id, ea.group_id) AS group_id,
                   COALESCE(ue.notify_enabled, 1) AS email_notify_enabled,
                   COALESCE(g.name, '') AS group_name,
                   COALESCE(g.notify_enabled, 1) AS group_notify_enabled,
                   COALESCE(ea.telegram_enabled, 1) AS account_telegram_enabled
            FROM fetched_messages m
            JOIN usable_emails ue ON ue.id = m.usable_email_id AND ue.user_id = m.user_id
            LEFT JOIN email_accounts ea ON ea.id = m.email_account_id AND ea.user_id = m.user_id
            LEFT JOIN groups g ON g.id = COALESCE(ue.group_id, ea.group_id)
                              AND g.user_id = ue.user_id
            WHERE m.id IN ({placeholders})
            ORDER BY m.id
            """,
            tuple(message_ids),
        ).fetchall()
    return [_row_to_event(row) for row in rows]


def load_message_event(settings: Settings, message_id: int) -> StoredMessageEvent | None:
    events: list[StoredMessageEvent] = load_message_events(settings, (message_id,))
    return events[0] if events else None


def event_channels(
    event: StoredMessageEvent,
    config: DeliveryConfig,
) -> tuple[DeliveryChannel, ...]:
    if not event.email_notify_enabled or not event.group_notify_enabled:
        return ()
    channels: list[DeliveryChannel] = []
    if config.email_enabled:
        channels.append("email")
    if config.telegram_enabled and event.account_telegram_enabled:
        channels.append("telegram")
    if config.webhook_enabled:
        channels.append("webhook")
    if config.script_enabled:
        channels.append("script")
    return tuple(channels)


def enqueue_delivery_jobs(settings: Settings, message_ids: Sequence[int]) -> int:
    config: DeliveryConfig = load_delivery_config(settings)
    events: list[StoredMessageEvent] = load_message_events(settings, message_ids)
    queued: int = 0
    with connect(settings) as connection:
        for event in events:
            for channel in event_channels(event, config):
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO message_deliveries (fetched_message_id, channel)"
                    " VALUES (?, ?)",
                    (event.id, channel),
                )
                queued += max(cursor.rowcount, 0)
    return queued


def claim_delivery_jobs(
    settings: Settings,
    message_ids: Sequence[int] | None = None,
) -> list[DeliveryJob]:
    params: list[object] = [MAX_DELIVERY_ATTEMPTS]
    message_filter: str = ""
    if message_ids:
        message_filter = f" AND fetched_message_id IN ({_placeholders(message_ids)})"
        params.extend(message_ids)
    claimed: list[DeliveryJob] = []
    with connect(settings) as connection:
        connection.execute(
            "UPDATE message_deliveries SET status = 'failed', last_error = 'stale delivery claim'"
            " WHERE status = 'sending' AND updated_at < datetime('now', '-5 minutes')"
        )
        rows = connection.execute(
            "SELECT id, fetched_message_id, channel, attempts FROM message_deliveries"
            " WHERE status IN ('pending', 'failed') AND attempts < ?"
            f"{message_filter} ORDER BY id LIMIT 100",
            tuple(params),
        ).fetchall()
        for row in rows:
            cursor = connection.execute(
                "UPDATE message_deliveries"
                " SET status = 'sending', attempts = attempts + 1, updated_at = datetime('now')"
                " WHERE id = ? AND status IN ('pending', 'failed')",
                (row["id"],),
            )
            if cursor.rowcount > 0:
                claimed.append(
                    DeliveryJob(
                        id=row["id"],
                        fetched_message_id=row["fetched_message_id"],
                        channel=row["channel"],
                        attempts=int(row["attempts"]) + 1,
                    )
                )
    return claimed


def mark_delivery_sent(settings: Settings, job_id: int) -> None:
    with connect(settings) as connection:
        connection.execute(
            "UPDATE message_deliveries SET status = 'sent', last_error = '',"
            " updated_at = datetime('now'), delivered_at = datetime('now') WHERE id = ?",
            (job_id,),
        )


def mark_delivery_failed(settings: Settings, job_id: int, error: str) -> None:
    with connect(settings) as connection:
        connection.execute(
            "UPDATE message_deliveries SET status = 'failed', last_error = ?,"
            " updated_at = datetime('now') WHERE id = ?",
            (error[:1000], job_id),
        )


def mark_delivery_skipped(settings: Settings, job_id: int, reason: str) -> None:
    with connect(settings) as connection:
        connection.execute(
            "UPDATE message_deliveries SET status = 'skipped', last_error = ?,"
            " updated_at = datetime('now') WHERE id = ?",
            (reason[:1000], job_id),
        )


def delivery_status(settings: Settings) -> dict[str, object]:
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT status, COUNT(*) AS count FROM message_deliveries GROUP BY status"
        ).fetchall()
        latest_failure = connection.execute(
            "SELECT last_error, updated_at FROM message_deliveries"
            " WHERE status = 'failed' ORDER BY updated_at DESC, id DESC LIMIT 1"
        ).fetchone()
    counts: dict[str, int] = {str(row["status"]): int(row["count"]) for row in rows}
    return {
        "pending": counts.get("pending", 0),
        "sending": counts.get("sending", 0),
        "sent": counts.get("sent", 0),
        "failed": counts.get("failed", 0),
        "skipped": counts.get("skipped", 0),
        "last_error": str(latest_failure["last_error"] or "") if latest_failure else "",
        "last_error_at": str(latest_failure["updated_at"] or "") if latest_failure else "",
    }
