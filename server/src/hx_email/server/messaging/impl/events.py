"""OneBot event/message conversion helpers."""

from __future__ import annotations

import json
from typing import Any

from hx_email.server.messaging.types import MessagingMessage


def ingest_event(payload: dict[str, Any]) -> MessagingMessage | None:
    """Convert an OneBot v11 event payload into a unified inbound message.

    仅处理消息事件(private/group);其他事件(通知,请求)返回 None。
    """
    post_type: str = str(payload.get("post_type", ""))
    if post_type != "message":
        return None
    message_type: str = str(payload.get("message_type", "private"))
    chat_id: str = str(payload.get("group_id") or payload.get("user_id") or "")
    if not chat_id:
        return None
    sender: Any = payload.get("sender") or {}
    raw_message: Any = payload.get("raw_message") or payload.get("message") or ""
    text: str = (
        raw_message if isinstance(raw_message, str) else json.dumps(raw_message, ensure_ascii=False)
    )
    return MessagingMessage(
        direction="inbound",
        chat_id=chat_id,
        chat_type="group" if message_type == "group" else "private",
        sender_id=str(payload.get("user_id", "")),
        sender_name=str(sender.get("nickname", "") if isinstance(sender, dict) else ""),
        text=text,
        message_id=str(payload.get("message_id", "")),
        raw=payload,
    )


def onebot_message_to_unified(
    item: dict[str, Any],
    direction: str,
) -> MessagingMessage:
    """Convert one OneBot message record into a unified message."""
    raw_message: Any = item.get("raw_message") or item.get("message") or ""
    text: str = raw_message if isinstance(raw_message, str) else _segments_text(raw_message)
    sender: Any = item.get("sender") or {}
    return MessagingMessage(
        direction=direction,
        chat_id=str(item.get("group_id") or item.get("user_id") or ""),
        chat_type="group" if item.get("group_id") else "private",
        sender_id=str(item.get("user_id", "")),
        sender_name=str(sender.get("nickname", "") if isinstance(sender, dict) else ""),
        text=text,
        message_id=str(item.get("message_id", "")),
        raw=item,
        created_at=str(item.get("time", "")),
    )


def _segments_text(segments: object) -> str:
    """Flatten OneBot message segments into plain text."""
    if isinstance(segments, str):
        return segments
    if not isinstance(segments, list):
        return str(segments)
    parts: list[str] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        segment_type: str = str(segment.get("type", "text"))
        data: Any = segment.get("data") or {}
        if segment_type == "text":
            parts.append(str(data.get("text", "")) if isinstance(data, dict) else "")
        else:
            parts.append(f"[{segment_type}]")
    return " ".join(part for part in parts if part)
