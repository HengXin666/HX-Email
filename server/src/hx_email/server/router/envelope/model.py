"""The unified envelope and inbound validation (spec section 3.1).

Only structure and validation live here. Mapping QQ or GitHub payloads to envelope dicts
is each provider's job; the router validates them with :func:`validate_inbound`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, cast

from hx_email.server.router.envelope.session import (
    DIRECTIONS,
    Direction,
    SessionAddress,
    parse_session,
)
from hx_email.server.router.errors import SessionNotFoundError

MESSAGE_ID_PREFIX: Final[str] = "m_"
ISO_UTC_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"
)


class EnvelopeError(ValueError):
    """A provider produced an envelope dict that breaks the spec 3.1 structure."""


@dataclass(frozen=True)
class Sender:
    id: str
    name: str = ""
    is_self: bool = False


@dataclass(frozen=True)
class Attachment:
    """A reference only; content is never stored."""

    kind: str
    url: str = ""
    name: str = ""
    size: int = 0


@dataclass(frozen=True)
class InboundMessage:
    """A validated provider envelope dict, ready to store."""

    session: SessionAddress
    direction: Direction
    sender: Sender
    text: str
    platform_message_id: str
    occurred_at: str
    dedup_key: str
    reply_to: str = ""
    attachments: tuple[Attachment, ...] = ()
    raw: dict[str, object] | None = None
    edit: bool = False


@dataclass(frozen=True)
class Envelope:
    """Spec 3.1 envelope as returned to MCP and REST consumers."""

    id: str
    cursor: str
    platform: str
    instance_id: int
    session: str
    session_type: str
    direction: str
    sender: Sender
    text: str
    reply_to: str
    platform_message_id: str
    attachments: tuple[Attachment, ...]
    occurred_at: str
    received_at: str
    raw: dict[str, object] | None = None
    raw_ref: str = ""

    def to_dict(self, include_raw: bool = False) -> dict[str, object]:
        return {
            "id": self.id,
            "cursor": self.cursor,
            "platform": self.platform,
            "instance_id": self.instance_id,
            "session": self.session,
            "session_type": self.session_type,
            "direction": self.direction,
            "sender": {
                "id": self.sender.id,
                "name": self.sender.name,
                "is_self": self.sender.is_self,
            },
            "text": self.text,
            "reply_to": self.reply_to,
            "platform_message_id": self.platform_message_id,
            "attachments": [attachment_to_dict(item) for item in self.attachments],
            "occurred_at": self.occurred_at,
            "received_at": self.received_at,
            "raw": self.raw if include_raw else None,
            "raw_ref": self.raw_ref,
        }


def attachment_to_dict(item: Attachment) -> dict[str, object]:
    return {"kind": item.kind, "url": item.url, "name": item.name, "size": item.size}


def require_str(data: dict[str, object], key: str, allow_empty: bool = False) -> str:
    if key not in data:
        raise EnvelopeError(f"missing field: {key}")
    value: object = data[key]
    if not isinstance(value, str):
        raise EnvelopeError(f"field {key} must be a string")
    if not allow_empty and not value:
        raise EnvelopeError(f"field {key} must not be empty")
    return value


def parse_sender(value: object) -> Sender:
    if not isinstance(value, dict):
        raise EnvelopeError("missing field: sender")
    sender_data: dict[str, object] = cast(dict[str, object], value)
    is_self: object = sender_data.get("is_self", False)
    if not isinstance(is_self, bool):
        raise EnvelopeError("field sender.is_self must be a boolean")
    return Sender(
        id=require_str(sender_data, "id"),
        name=require_str(sender_data, "name", allow_empty=True),
        is_self=is_self,
    )


def parse_attachments(value: object) -> tuple[Attachment, ...]:
    if not isinstance(value, list):
        raise EnvelopeError("field attachments must be a list")
    result: list[Attachment] = []
    for item in value:
        if not isinstance(item, dict):
            raise EnvelopeError("attachment must be an object")
        data: dict[str, object] = cast(dict[str, object], item)
        size: object = data.get("size", 0)
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise EnvelopeError("attachment.size must be a non-negative integer")
        result.append(
            Attachment(
                kind=require_str(data, "kind"),
                url=str(data.get("url", "")),
                name=str(data.get("name", "")),
                size=size,
            )
        )
    return tuple(result)


def validate_inbound(data: dict[str, object], instance_id: int) -> InboundMessage:
    """Check one ``parse_event`` dict against spec 3.1 and bind it to ``instance_id``."""
    try:
        session: SessionAddress = parse_session(require_str(data, "session"))
    except SessionNotFoundError as error:
        raise EnvelopeError(error.message) from error
    if session.instance_id != instance_id:
        raise EnvelopeError("session instance does not match the receiving instance")
    direction: str = str(data.get("direction", "inbound"))
    if direction not in DIRECTIONS:
        raise EnvelopeError(f"invalid direction: {direction}")
    occurred_at: str = require_str(data, "occurred_at")
    if not ISO_UTC_PATTERN.match(occurred_at):
        raise EnvelopeError("occurred_at must be ISO 8601 UTC ending with Z")
    raw: object = data.get("raw")
    if raw is not None and not isinstance(raw, dict):
        raise EnvelopeError("field raw must be an object or null")
    edit: object = data.get("edit", False)
    if not isinstance(edit, bool):
        raise EnvelopeError("field edit must be a boolean")
    return InboundMessage(
        session=session,
        direction=cast(Direction, direction),
        sender=parse_sender(data.get("sender")),
        text=require_str(data, "text", allow_empty=True),
        platform_message_id=require_str(data, "platform_message_id"),
        occurred_at=occurred_at,
        dedup_key=require_str(data, "dedup_key"),
        reply_to=str(data.get("reply_to", "")),
        attachments=parse_attachments(data.get("attachments", [])),
        raw=cast(dict[str, object] | None, raw),
        edit=edit,
    )
