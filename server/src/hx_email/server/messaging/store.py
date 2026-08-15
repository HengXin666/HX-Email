"""Persistence for messaging plugin instances and ingested messages."""

from __future__ import annotations

import json

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.security import encrypt_secret
from hx_email.server.messaging.impl.rows import row_to_instance, safe_json
from hx_email.server.messaging.types import ChatType, MessagingInstance, MessagingMessage

STATUS_STOPPED: str = "stopped"

QQ_DEFAULT_API_BASE_URL: str = "http://127.0.0.1:3000"
QQ_DEFAULT_WEBUI_URL: str = "http://127.0.0.1:6099/webui"


def create_instance(
    settings: Settings,
    user_id: int,
    kind: str,
    name: str,
    config: dict[str, str],
) -> MessagingInstance:
    config = with_qq_defaults(kind, config)
    encrypted: str = encrypt_secret(settings, json.dumps(config, ensure_ascii=False))
    with connect(settings) as connection:
        cursor = connection.execute(
            """
            INSERT INTO messaging_instances (user_id, kind, name, status, config_encrypted)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, kind, name, STATUS_STOPPED, encrypted),
        )
        last_id: int | None = cursor.lastrowid
        if last_id is None:
            raise RuntimeError("Failed to create messaging instance")
        instance_id: int = last_id
    return get_instance(settings, user_id, instance_id)  # type: ignore[return-value]


def get_instance(
    settings: Settings,
    user_id: int,
    instance_id: int,
) -> MessagingInstance | None:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT * FROM messaging_instances WHERE id = ? AND user_id = ?",
            (instance_id, user_id),
        ).fetchone()
    return row_to_instance(row, settings) if row is not None else None


def list_instances(settings: Settings, user_id: int) -> list[MessagingInstance]:
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT * FROM messaging_instances WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
    return [row_to_instance(row, settings) for row in rows]


def get_instance_by_id(settings: Settings, instance_id: int) -> MessagingInstance | None:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT * FROM messaging_instances WHERE id = ?",
            (instance_id,),
        ).fetchone()
    return row_to_instance(row, settings) if row is not None else None


def update_instance_status(settings: Settings, instance_id: int, status: str) -> None:
    with connect(settings) as connection:
        connection.execute(
            """
            UPDATE messaging_instances
            SET status = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (status, instance_id),
        )


def update_instance_config(
    settings: Settings,
    user_id: int,
    instance_id: int,
    config: dict[str, str],
) -> MessagingInstance | None:
    encrypted: str = encrypt_secret(settings, json.dumps(config, ensure_ascii=False))
    with connect(settings) as connection:
        connection.execute(
            """
            UPDATE messaging_instances
            SET config_encrypted = ?, updated_at = datetime('now')
            WHERE id = ? AND user_id = ?
            """,
            (encrypted, instance_id, user_id),
        )
    return get_instance(settings, user_id, instance_id)


def delete_instance(settings: Settings, user_id: int, instance_id: int) -> bool:
    with connect(settings) as connection:
        connection.execute(
            "DELETE FROM messaging_messages WHERE instance_id = ?",
            (instance_id,),
        )
        cursor = connection.execute(
            "DELETE FROM messaging_instances WHERE id = ? AND user_id = ?",
            (instance_id, user_id),
        )
    return cursor.rowcount > 0


def save_message(
    settings: Settings,
    instance_id: int,
    message: MessagingMessage,
) -> int:
    with connect(settings) as connection:
        cursor = connection.execute(
            """
            INSERT INTO messaging_messages (
                instance_id, direction, chat_id, chat_type, sender_id,
                sender_name, text, message_id, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                instance_id,
                message.direction,
                message.chat_id,
                message.chat_type,
                message.sender_id,
                message.sender_name,
                message.text,
                message.message_id,
                json.dumps(message.raw, ensure_ascii=False),
            ),
        )
        last_id: int | None = cursor.lastrowid
        if last_id is None:
            raise RuntimeError("Failed to store messaging message")
        return last_id


def list_messages(
    settings: Settings,
    user_id: int,
    instance_id: int,
    chat_id: str = "",
    limit: int = 50,
) -> list[MessagingMessage]:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT user_id FROM messaging_instances WHERE id = ?",
            (instance_id,),
        ).fetchone()
        if row is None or int(row["user_id"]) != user_id:
            return []
        if chat_id:
            rows = connection.execute(
                """
                SELECT * FROM messaging_messages
                WHERE instance_id = ? AND chat_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (instance_id, chat_id, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT * FROM messaging_messages
                WHERE instance_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (instance_id, limit),
            ).fetchall()
    result: list[MessagingMessage] = []
    for r in rows:
        chat_type_value: str = str(r["chat_type"])
        result.append(
            MessagingMessage(
                direction=str(r["direction"]),
                chat_id=str(r["chat_id"]),
                chat_type=normalize_chat_type(chat_type_value),
                sender_id=str(r["sender_id"]),
                sender_name=str(r["sender_name"]),
                text=str(r["text"]),
                message_id=str(r["message_id"]),
                created_at=str(r["created_at"]),
                raw=safe_json(str(r["raw_json"])),
            )
        )
    return result


def find_instance_by_event_token(
    settings: Settings,
    kind: str,
    token: str,
) -> MessagingInstance | None:
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT * FROM messaging_instances WHERE kind = ?",
            (kind,),
        ).fetchall()
    for row in rows:
        instance = row_to_instance(row, settings)
        if instance.config.get("event_token", "") == token:
            return instance
    return None


def normalize_chat_type(value: str) -> ChatType:
    if value == "group":
        return "group"
    if value == "channel":
        return "channel"
    return "private"


def with_qq_defaults(kind: str, config: dict[str, str]) -> dict[str, str]:
    """Fill local NapCat defaults and generate an event token for QQ instances."""
    import secrets

    if kind != "qq":
        return dict(config)
    defaults: dict[str, str] = dict(config)
    if not defaults.get("api_base_url"):
        defaults["api_base_url"] = QQ_DEFAULT_API_BASE_URL
    if not defaults.get("webui_url"):
        defaults["webui_url"] = QQ_DEFAULT_WEBUI_URL
    if not defaults.get("event_token"):
        defaults["event_token"] = secrets.token_hex(16)
    if not defaults.get("embedded_engine"):
        defaults["embedded_engine"] = "true"
    return defaults
