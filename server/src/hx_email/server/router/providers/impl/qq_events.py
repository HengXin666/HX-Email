"""OneBot 11 inbound event parsing and QQ session addresses.

Address grammar: docs/messaging-router.md section 2, `qq:<instance_id>:<session_type>:<peer>`.
Envelope mapping: docs/messaging-router.md section 3.3. Only `post_type == "message"`
becomes an envelope; notice, request and meta_event are dropped with a debug log.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime

from hx_email.server.router.providers.impl.qq_types import (
    QQ_SESSION_TYPES,
    InvalidSessionError,
    QQSession,
    QQSessionType,
)

LOGGER: logging.Logger = logging.getLogger(__name__)

PLATFORM: str = "qq"
DIGITS: re.Pattern[str] = re.compile(r"^[0-9]+$")
TEMP_PEER: re.Pattern[str] = re.compile(r"^([0-9]+)-([0-9]+)$")


def session_address(instance_id: int, session_type: QQSessionType, peer: str) -> str:
    """Build a QQ session address; `peer` for temp is `<group_id>-<user_id>`."""
    if instance_id <= 0:
        raise InvalidSessionError(f"instance_id must be positive: {instance_id}")
    if session_type not in QQ_SESSION_TYPES:
        raise InvalidSessionError(f"unknown QQ session_type: {session_type}")
    pattern: re.Pattern[str] = TEMP_PEER if session_type == "temp" else DIGITS
    if not pattern.match(peer):
        raise InvalidSessionError(f"invalid peer for {session_type}: {peer}")
    return f"{PLATFORM}:{instance_id}:{session_type}:{peer}"


def parse_session_address(address: str) -> QQSession:
    """Reverse an address: split on the first three colons, 4th part is the peer."""
    parts: list[str] = address.split(":", 3)
    if len(parts) != 4 or parts[0] != PLATFORM or not DIGITS.match(parts[1]):
        raise InvalidSessionError(f"not a QQ session address: {address}")
    instance_id: int = int(parts[1])
    raw_type: str = parts[2]
    peer: str = parts[3]
    if raw_type == "private" and DIGITS.match(peer):
        return QQSession(address, instance_id, "private", peer_user_id=peer)
    if raw_type == "group" and DIGITS.match(peer):
        return QQSession(address, instance_id, "group", peer_group_id=peer)
    temp_match: re.Match[str] | None = TEMP_PEER.match(peer)
    if raw_type == "temp" and temp_match is not None:
        return QQSession(
            address,
            instance_id,
            "temp",
            peer_user_id=temp_match.group(2),
            peer_group_id=temp_match.group(1),
        )
    raise InvalidSessionError(f"not a QQ session address: {address}")


def dedup_key(message_id: object, event_time: object) -> str:
    """Inbound dedup key `qq:<message_id>:<time>` (router 7.5)."""
    return f"{PLATFORM}:{message_id}:{int(str(event_time))}"


def unix_to_iso(event_time: object) -> str:
    """OneBot `time` (Unix seconds) to ISO 8601 UTC ending in Z."""
    moment: datetime = datetime.fromtimestamp(int(str(event_time)), tz=UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def as_mapping(value: object) -> Mapping[str, object]:
    """Return `value` if it is a str-keyed mapping, else an empty dict."""
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def temp_group_id(event: Mapping[str, object]) -> str:
    """Source group of a temp session. Field position 需复核 (qq-napcat 4.1).

    Checked in order: top-level `group_id`, then `sender.group_id`.
    """
    for source in (event, as_mapping(event.get("sender"))):
        value: str = str(source.get("group_id") or "")
        if DIGITS.match(value):
            return value
    return ""


def event_session(instance_id: int, event: Mapping[str, object]) -> tuple[QQSessionType, str]:
    """Map message_type and sub_type to (session_type, address), router 3.3."""
    message_type: str = str(event.get("message_type", ""))
    user_id: str = str(event.get("user_id", ""))
    if message_type == "group":
        group_id: str = str(event.get("group_id", ""))
        return "group", session_address(instance_id, "group", group_id)
    if message_type != "private":
        raise InvalidSessionError(f"unsupported message_type: {message_type}")
    if str(event.get("sub_type", "friend")) == "group":
        source_group: str = temp_group_id(event)
        peer: str = f"{source_group}-{user_id}"
        return "temp", session_address(instance_id, "temp", peer)
    return "private", session_address(instance_id, "private", user_id)


def flatten_segments(segments: object) -> tuple[str, list[dict[str, object]], str]:
    """Return (text, attachments, reply_to) from an OneBot segment array.

    text segments are concatenated as-is, at becomes `@<qq>` (`@all` for all),
    image becomes an `[image]` placeholder plus an attachment reference, reply is
    taken out of the text into reply_to, other types become `[<type>]`.
    """
    if isinstance(segments, str):
        return segments, [], ""
    parts: list[str] = []
    attachments: list[dict[str, object]] = []
    reply_to: str = ""
    items: list[object] = list(segments) if isinstance(segments, list) else []
    for item in items:
        segment: Mapping[str, object] = as_mapping(item)
        segment_type: str = str(segment.get("type", ""))
        data: Mapping[str, object] = as_mapping(segment.get("data"))
        if segment_type == "text":
            parts.append(str(data.get("text", "")))
        elif segment_type == "at":
            target: str = str(data.get("qq", ""))
            parts.append("@all" if target == "all" else f"@{target}")
        elif segment_type == "image":
            parts.append("[image]")
            attachments.append(image_attachment(data))
        elif segment_type == "reply":
            reply_to = str(data.get("id", ""))
        elif segment_type:
            parts.append(f"[{segment_type}]")
    return "".join(parts), attachments, reply_to


def image_attachment(data: Mapping[str, object]) -> dict[str, object]:
    """Attachment reference `{kind, url, name, size}` (router 3.1); content is not fetched."""
    size_text: str = str(data.get("file_size") or "0")
    return {
        "kind": "image",
        "url": str(data.get("url", "")),
        "name": str(data.get("file", "")),
        "size": int(size_text) if DIGITS.match(size_text) else 0,
    }


def to_envelope(instance_id: int, event: Mapping[str, object]) -> dict[str, object] | None:
    """Convert one OneBot 11 event into a router envelope, or None when dropped.

    `id`, `cursor` and `received_at` are assigned by the router when it stores the row.
    """
    post_type: str = str(event.get("post_type", ""))
    if post_type != "message":
        LOGGER.debug("drop onebot event post_type=%s instance=%s", post_type, instance_id)
        return None
    try:
        session_type, address = event_session(instance_id, event)
        key: str = dedup_key(event["message_id"], event["time"])
        occurred_at: str = unix_to_iso(event["time"])
    except (InvalidSessionError, KeyError, ValueError) as error:
        LOGGER.debug("drop malformed onebot message instance=%s: %s", instance_id, error)
        return None
    sender: Mapping[str, object] = as_mapping(event.get("sender"))
    user_id: str = str(event.get("user_id", ""))
    text, attachments, reply_to = flatten_segments(event.get("message"))
    return {
        "platform": PLATFORM,
        "instance_id": instance_id,
        "session": address,
        "session_type": session_type,
        "direction": "inbound",
        "sender": {
            "id": user_id,
            "name": str(sender.get("nickname", "")),
            "is_self": user_id != "" and user_id == str(event.get("self_id", "")),
        },
        "text": text,
        "reply_to": reply_to,
        "platform_message_id": str(event["message_id"]),
        "attachments": attachments,
        "occurred_at": occurred_at,
        "dedup_key": key,
        "raw": dict(event),
    }
