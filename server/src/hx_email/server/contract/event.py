"""Event envelope v2: the v1 envelope plus the fields a trigger needs (spec 3.5).

Added on top of every v1 field (which stay, so existing consumers keep working):

- ``address``: v2 address of the session the event belongs to
- ``thread``: v2 address of the conversation thread; today the session itself
- ``parent``: one level up (the repo of an issue, the account of a QQ chat)
- ``kind``: event kind; the one the provider stored with the row, else derived from the
  ``platform_message_id`` prefix by the platform's declaration (message, comment, ...)
- ``mentions``: structured mentions, ``[{"id", "name", "is_self"}]``
- ``flags``: ``from_self``, ``mention_self``, ``reply_to_self``; ``null`` means the signal
  was not recorded for this event (a row stored before the provider reported it, or a
  platform that does not declare it in ``signals``), which is different from ``false``
- ``segments``: ordered content parts, ``[{"type": "text", "text": ...}, ...]``

Providers that already know mentions or the reply target pass them in the envelope dict
under the same keys and they win over the derived defaults.
"""

from __future__ import annotations

from typing import Final

from hx_email.server.contract.address import Address, AddressError, from_legacy
from hx_email.server.contract.builtin import REGISTRY
from hx_email.server.contract.capabilities import PlatformCapabilities

FLAG_NAMES: Final[tuple[str, ...]] = ("from_self", "mention_self", "reply_to_self")
CONTRACT_VERSION: Final[int] = 2


def text_of(value: object) -> str:
    return value if isinstance(value, str) else ""


def sender_is_self(envelope: dict[str, object]) -> bool:
    sender: object = envelope.get("sender")
    return isinstance(sender, dict) and sender.get("is_self") is True


def derive_flags(envelope: dict[str, object]) -> dict[str, bool | None]:
    given: object = envelope.get("flags")
    provided: dict[str, object] = given if isinstance(given, dict) else {}
    flags: dict[str, bool | None] = {}
    for name in FLAG_NAMES:
        value: object = provided.get(name)
        if isinstance(value, bool):
            flags[name] = value
        elif name == "from_self":
            flags[name] = sender_is_self(envelope)
        else:
            # 没有存下这个信号 (旧行, 或平台未声明) 就是未知, 不冒充 false
            flags[name] = None
    return flags


def derive_segments(envelope: dict[str, object]) -> list[dict[str, object]]:
    given: object = envelope.get("segments")
    if isinstance(given, list) and given:
        return [item for item in given if isinstance(item, dict)]
    segments: list[dict[str, object]] = []
    reply_to: str = text_of(envelope.get("reply_to"))
    if reply_to:
        segments.append({"type": "reply", "id": reply_to})
    text: str = text_of(envelope.get("text"))
    if text:
        segments.append({"type": "text", "text": text})
    attachments: object = envelope.get("attachments")
    for item in attachments if isinstance(attachments, list) else []:
        if isinstance(item, dict):
            segments.append({"type": text_of(item.get("kind")) or "file", **item})
    return segments


# 触发信号以入库时 provider 给出的为准 (kind, mentions, flags), 旧行才按前缀与发送者推导
# 决策记录: .agents/notes/implemented/feature/2026-11-08-github-events-triggers.md
def event_view(envelope: dict[str, object]) -> dict[str, object]:
    """Return a copy of one v1 envelope dict carrying the v2 fields."""
    view: dict[str, object] = dict(envelope)
    caps: PlatformCapabilities | None = REGISTRY.get(text_of(envelope.get("platform")))
    try:
        address: Address | None = from_legacy(text_of(envelope.get("session")))
    except AddressError:
        address = None
    view["contract"] = CONTRACT_VERSION
    view["address"] = address.text if address is not None else ""
    view["thread"] = view["address"]
    view["parent"] = address.parent.text if address is not None else ""
    view["kind"] = text_of(envelope.get("kind")) or (
        caps.event_kind(text_of(envelope.get("platform_message_id")))
        if caps is not None
        else "message"
    )
    mentions: object = envelope.get("mentions")
    view["mentions"] = mentions if isinstance(mentions, list) else []
    view["flags"] = derive_flags(envelope)
    view["segments"] = derive_segments(envelope)
    return view
