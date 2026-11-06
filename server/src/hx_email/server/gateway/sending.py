"""Sending side of the gateway: ``message_send``, ``delivery_status``, hold and resume.

Every outbound path (MCP, REST, the web console) ends here, so idempotency, shaping and
the breaker are one guarantee rather than one per caller. The call is synchronous and
asynchronous at once: the row is queued first, then the caller may wait up to
``wait_seconds`` for the dispatcher's outcome; ``wait_seconds=0`` returns ``queued``
immediately and the caller polls ``delivery_status`` (or simply trusts the outbox).
"""

from __future__ import annotations

import sqlite3
import uuid
from typing import Final

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.gateway.impl.breaker import BREAKER
from hx_email.server.gateway.impl.dispatch import DISPATCHER
from hx_email.server.gateway.providers import InstanceRow, profile_for, require_owned
from hx_email.server.router.envelope import SessionAddress, parse_session
from hx_email.server.router.errors import (
    SessionNotFoundError,
    SessionNotSendableError,
    TextTooLongError,
)
from hx_email.server.router.impl.outbox import EnqueueResult, Entry, enqueue_send
from hx_email.server.router.impl.outbox_admin import find_send, get_entry, set_instance_held

MAX_WAIT_SECONDS: Final[float] = 5.0
QQ_TYPES: Final[frozenset[str]] = frozenset({"private", "group", "temp"})
GITHUB_TYPES: Final[frozenset[str]] = frozenset({"issue", "repo"})


def iso(stamp: str) -> str:
    return stamp.replace(" ", "T") + "Z" if stamp and "T" not in stamp else stamp


def delivery_view(entry: Entry, deduplicated: bool = False) -> dict[str, object]:
    return {
        "delivery_id": entry.delivery_id,
        "kind": entry.kind,
        "sink": entry.session,
        "status": entry.status,
        "deduplicated": deduplicated,
        "attempts": entry.attempts,
        "platform_message_id": entry.platform_message_id,
        "queued_until": iso(entry.next_attempt_at) if entry.status == "queued" else "",
        "last_error": entry.last_error,
    }


def check_sendable(instance: InstanceRow, address: SessionAddress, title: str) -> None:
    allowed: frozenset[str] = QQ_TYPES if instance.kind == "qq" else GITHUB_TYPES
    if address.session_type not in allowed:
        raise SessionNotSendableError(f"{address.session_type} sessions cannot be sent to")
    if address.session_type == "repo" and not title.strip():
        raise SessionNotSendableError("sending to a repository opens an issue and needs a title")


# 所有出站 (MCP, REST, 前端) 都在这里入队, 幂等, 整形与熔断只有一份; 先入队再按 wait_seconds 等结果
# 决策记录: .agents/notes/implemented/feature/2026-11-06-router-gateway-facade.md
def send_message(
    settings: Settings,
    user_id: int,
    sink: str,
    text: str,
    idempotency_key: str = "",
    *,
    title: str = "",
    reply_to: str = "",
    wait_seconds: float = MAX_WAIT_SECONDS,
) -> dict[str, object]:
    address: SessionAddress = parse_session(sink)
    instance: InstanceRow = require_owned(settings, user_id, address.instance_id)
    if instance.kind != address.platform:
        raise SessionNotFoundError(f"{sink} does not match instance platform {instance.kind}")
    if not text.strip():
        raise SessionNotSendableError("text must not be empty")
    limit: int = profile_for(instance).max_text_length
    if len(text) > limit:
        raise TextTooLongError(f"text is {len(text)} characters, limit is {limit}")
    check_sendable(instance, address, title)
    key: str = idempotency_key or f"auto-{uuid.uuid4().hex}"
    held: bool = BREAKER.is_manual(instance.id)
    result: EnqueueResult = enqueue_send(
        settings,
        user_id,
        instance.id,
        address.address,
        {"text": text, "title": title, "reply_to": reply_to},
        key,
        held=held,
    )
    entry: Entry = result.entry
    if not held and entry.status == "queued":
        DISPATCHER.wake(settings)
    wait: float = min(max(wait_seconds, 0.0), MAX_WAIT_SECONDS)
    if wait > 0 and entry.status in ("queued", "sending"):
        entry = DISPATCHER.wait_for(settings, entry.id, wait) or entry
    return delivery_view(entry, result.deduplicated)


def owner_of(settings: Settings, delivery_id: int) -> int | None:
    with connect(settings) as connection:
        row: sqlite3.Row | None = connection.execute(
            "SELECT user_id FROM router_outbox WHERE id = ?", (delivery_id,)
        ).fetchone()
    return None if row is None else int(row["user_id"])


def parse_delivery_id(value: str) -> int:
    digits: str = value[2:] if value.startswith("d_") else value
    if not digits.isdigit():
        raise SessionNotFoundError(f"invalid delivery id: {value!r}")
    return int(digits)


def delivery_status(
    settings: Settings,
    user_id: int,
    *,
    delivery_id: str = "",
    idempotency_key: str = "",
    sink: str = "",
) -> dict[str, object] | None:
    """One delivery by id, or by ``(idempotency_key, sink)``; None when it is not ours."""
    entry: Entry | None
    if delivery_id:
        row_id: int = parse_delivery_id(delivery_id)
        if owner_of(settings, row_id) != user_id:
            return None
        entry = get_entry(settings, row_id)
    else:
        address: SessionAddress = parse_session(sink)
        require_owned(settings, user_id, address.instance_id)
        entry = find_send(settings, address.instance_id, idempotency_key)
    return None if entry is None else delivery_view(entry)


def hold_outbound(settings: Settings, user_id: int, instance_id: int) -> dict[str, object]:
    instance: InstanceRow = require_owned(settings, user_id, instance_id)
    BREAKER.manual_hold(instance.id)
    parked: int = set_instance_held(settings, instance.id, True)
    return {"instance_id": instance.id, "outbound": "manual_hold", "parked": parked}


def resume_outbound(settings: Settings, user_id: int, instance_id: int) -> dict[str, object]:
    instance: InstanceRow = require_owned(settings, user_id, instance_id)
    BREAKER.resume(instance.id)
    released: int = set_instance_held(settings, instance.id, False)
    if released:
        DISPATCHER.wake(settings)
    return {"instance_id": instance.id, "outbound": "open", "released": released}
