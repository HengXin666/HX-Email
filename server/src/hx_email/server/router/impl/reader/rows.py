"""Stored rows of ``messaging_messages`` back to spec 3.1 envelopes."""

from __future__ import annotations

import json
import sqlite3

from hx_email.config import Settings
from hx_email.server.router.cursor import encode_cursor
from hx_email.server.router.envelope import (
    Attachment,
    Envelope,
    Sender,
    iso_utc_from_sqlite,
    parse_session,
)
from hx_email.server.router.impl.store import read_raw

# 旧写入路径只存纯号, 补地址时要一个平台名; messaging_instances.kind 到这里只有 qq.
PLATFORM_OF_KIND: str = "qq"


def decode_attachments(raw: str) -> tuple[Attachment, ...]:
    """Decode the stored attachment list; a malformed value yields none rather than an error."""
    if not raw:
        return ()
    try:
        parsed: object = json.loads(raw)
    except ValueError:
        return ()
    if not isinstance(parsed, list):
        return ()
    out: list[Attachment] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        size_value: object = item.get("size") or 0
        out.append(
            Attachment(
                kind=str(item.get("kind") or ""),
                url=str(item.get("url") or ""),
                name=str(item.get("name") or ""),
                size=size_value if isinstance(size_value, int) else 0,
            )
        )
    return tuple(out)


def row_to_envelope(settings: Settings, row: sqlite3.Row, include_raw: bool) -> Envelope:
    message_id: int = int(row["id"])
    instance_id: int = int(row["instance_id"])
    chat_id: str = str(row["chat_id"])
    if ":" not in chat_id:
        # 旧写入路径存的是纯号, 补齐成完整地址再解析, 否则整页都读不出来.
        stored_type: str = str(row["chat_type"] or "private")
        chat_id = f"{PLATFORM_OF_KIND}:{instance_id}:{stored_type}:{chat_id}"
    address = parse_session(chat_id)
    raw: dict[str, object] | None = None
    if include_raw:
        raw = read_raw(
            settings,
            instance_id,
            message_id,
            str(row["raw_json"] or ""),
            str(row["raw_ref"] or ""),
        )
    return Envelope(
        id=f"m_{message_id}",
        cursor=encode_cursor(instance_id, message_id),
        platform=address.platform,
        instance_id=instance_id,
        session=chat_id,
        session_type=address.session_type,
        direction=str(row["direction"]),
        sender=Sender(
            id=str(row["sender_id"] or ""),
            name=str(row["sender_name"] or ""),
            is_self=bool(row["is_self"]),
        ),
        text=str(row["text"] or ""),
        reply_to=str(row["reply_to"] or ""),
        platform_message_id=str(row["message_id"] or ""),
        attachments=decode_attachments(str(row["attachments_json"] or "")),
        occurred_at=str(row["occurred_at"] or row["created_at"] or ""),
        received_at=iso_utc_from_sqlite(str(row["created_at"] or "")),
        raw=raw,
        raw_ref=str(row["raw_ref"] or ""),
    )
