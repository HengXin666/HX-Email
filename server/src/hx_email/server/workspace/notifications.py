"""Browser-notification polling: new-mail detection with per-email/per-group mute."""

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail.verification.extract import extract_verification_code

POLL_BATCH_LIMIT: int = 20


def poll_notifications(
    settings: Settings,
    user_id: int,
    since_id: int,
) -> dict[str, object]:
    """Return stored messages newer than since_id that should notify the user.

    since_id < 0 initializes the cursor: only latest_id is returned so old mail
    never floods the browser on first enable. Muted emails/groups are excluded
    from the notification list but still advance latest_id.
    """
    with connect(settings) as connection:
        latest_row = connection.execute(
            "SELECT COALESCE(MAX(id), 0) FROM fetched_messages WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        latest_id: int = int(latest_row[0])
        if since_id < 0:
            return {"latest_id": latest_id, "notifications": []}

        rows = connection.execute(
            """
            SELECT m.id, m.usable_email_id, ue.address, m.from_address, m.subject,
                   m.body, m.received_at, m.created_at
            FROM fetched_messages m
            JOIN usable_emails ue ON ue.id = m.usable_email_id
            LEFT JOIN groups g ON g.id = ue.group_id AND g.user_id = ue.user_id
            WHERE m.user_id = ? AND m.id > ?
              AND COALESCE(ue.notify_enabled, 1) = 1
              AND COALESCE(g.notify_enabled, 1) = 1
            ORDER BY m.id
            LIMIT ?
            """,
            (user_id, since_id, POLL_BATCH_LIMIT),
        ).fetchall()

    notifications: list[dict[str, object]] = [
        {
            "id": row["id"],
            "usable_email_id": row["usable_email_id"],
            "address": row["address"],
            "from_address": row["from_address"],
            "subject": row["subject"],
            "verification_code": extract_verification_code(
                f"{row['subject']}\n{row['body'] or ''}"
            ),
            "received_at": row["received_at"] or row["created_at"],
        }
        for row in rows
    ]
    # A full batch may have newer rows left; only advance past what was returned
    if len(notifications) == POLL_BATCH_LIMIT:
        latest_id = int(rows[-1]["id"])
    return {"latest_id": latest_id, "notifications": notifications}


def set_email_notify(settings: Settings, user_id: int, usable_email_id: int, enabled: bool) -> bool:
    with connect(settings) as connection:
        result = connection.execute(
            "UPDATE usable_emails SET notify_enabled = ? WHERE id = ? AND user_id = ?",
            (1 if enabled else 0, usable_email_id, user_id),
        )
    return result.rowcount > 0


def set_group_notify(settings: Settings, user_id: int, group_id: int, enabled: bool) -> bool:
    with connect(settings) as connection:
        result = connection.execute(
            "UPDATE groups SET notify_enabled = ? WHERE id = ? AND user_id = ?",
            (1 if enabled else 0, group_id, user_id),
        )
    return result.rowcount > 0
