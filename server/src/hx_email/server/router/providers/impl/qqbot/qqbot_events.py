"""QQ 官方机器人回调载荷到路由 envelope.

回调体是网关通用结构 ``{"id", "op", "d", "s", "t"}``: op 13 是回调地址验证, op 0 是事件推送.
本阶段只接子频道文字消息: ``AT_MESSAGE_CREATE`` (公域, 只有 @ 机器人或回复机器人的消息) 与
``MESSAGE_CREATE`` (私域, 子频道全部消息). 会话是子频道:
v1 ``qqbot:<iid>:channel:<频道>/<子频道>``, v2 ``qqbot:<iid>/guild/<频道>/channel/<子频道>``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Final

JsonDict = dict[str, object]
OP_DISPATCH: Final[int] = 0
OP_ACK: Final[int] = 12
OP_VALIDATE: Final[int] = 13
AT_EVENT: Final[str] = "AT_MESSAGE_CREATE"
ALL_EVENT: Final[str] = "MESSAGE_CREATE"
HANDLED_EVENTS: Final[frozenset[str]] = frozenset({AT_EVENT, ALL_EVENT})
ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9]+$")
MENTION_PATTERN: Final[re.Pattern[str]] = re.compile(r"<@!?([0-9]+)>")


def as_dict(value: object) -> JsonDict:
    return {str(key): item for key, item in value.items()} if isinstance(value, Mapping) else {}


def as_list(value: object) -> list[JsonDict]:
    return [as_dict(item) for item in value] if isinstance(value, list) else []


def channel_session(instance_id: int, guild_id: str, channel_id: str) -> str:
    return f"qqbot:{instance_id}:channel:{guild_id}/{channel_id}"


def utc_z(value: object) -> str:
    """RFC 3339 (带时区) 到 UTC ``Z``; 解析不了时用当前时间."""
    try:
        moment: datetime = datetime.fromisoformat(str(value))
    except ValueError:
        moment = datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def render(content: str, mentions: list[JsonDict]) -> tuple[str, list[JsonDict]]:
    """``<@!id>`` 换成 ``@昵称``; 提到机器人 (``bot`` 为 true) 即提到本账号."""
    by_id: dict[str, JsonDict] = {str(item.get("id", "")): item for item in mentions}
    found: list[JsonDict] = []
    seen: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        user: JsonDict = by_id.get(match.group(1), {})
        name: str = str(user.get("username") or match.group(1))
        if match.group(1) not in seen:
            seen.add(match.group(1))
            found.append({"id": match.group(1), "name": name, "is_self": user.get("bot") is True})
        return f"@{name}"

    return MENTION_PATTERN.sub(replace, content).strip(), found


# 公域只推送 @机器人 或回复机器人的消息: 没有 @ 到机器人的那一类就是回复机器人
# 决策记录: .agents/notes/implemented/feature/2026-11-09-qqbot-guild.md
def message_envelope(instance_id: int, event: str, data: JsonDict) -> JsonDict | None:
    """一条子频道消息; 字段缺失或 id 形状不对时返回 None."""
    guild_id: str = str(data.get("guild_id") or "")
    channel_id: str = str(data.get("channel_id") or "")
    message_id: str = str(data.get("id") or "")
    if not (ID_PATTERN.match(guild_id) and ID_PATTERN.match(channel_id) and message_id):
        return None
    author: JsonDict = as_dict(data.get("author"))
    text, mentions = render(str(data.get("content") or ""), as_list(data.get("mentions")))
    mention_self: bool = any(item["is_self"] for item in mentions)
    reference: JsonDict = as_dict(data.get("message_reference"))
    reply_to: str = str(reference.get("message_id") or "")
    attachments: list[JsonDict] = [
        {
            "kind": "image" if str(item.get("content_type", "")).startswith("image") else "file",
            "url": str(item.get("url") or ""),
            "name": str(item.get("filename") or ""),
            "size": int(str(item.get("size") or 0)) if str(item.get("size") or 0).isdigit() else 0,
        }
        for item in as_list(data.get("attachments"))
    ]
    return {
        "platform": "qqbot",
        "instance_id": instance_id,
        "session": channel_session(instance_id, guild_id, channel_id),
        "session_type": "channel",
        "chat_type": "group",
        "direction": "inbound",
        "sender": {
            "id": str(author.get("id") or ""),
            "name": str(author.get("username") or ""),
            "is_self": False,
        },
        "text": text,
        "reply_to": reply_to,
        "platform_message_id": message_id,
        "dedup_key": f"qqbot:{message_id}",
        "attachments": attachments,
        "occurred_at": utc_z(data.get("timestamp")),
        "raw": {
            "event": event,
            "guild_id": guild_id,
            "channel_id": channel_id,
            "seq": data.get("seq"),
        },
        "kind": "message",
        "mentions": mentions,
        "flags": {
            "from_self": False,
            "mention_self": mention_self,
            "reply_to_self": event == AT_EVENT and not mention_self,
        },
    }


def payload_envelopes(instance_id: int, payload: JsonDict) -> list[JsonDict]:
    """op 0 的已处理事件到 envelope; 其它 op 与事件返回空列表."""
    if payload.get("op") != OP_DISPATCH or str(payload.get("t") or "") not in HANDLED_EVENTS:
        return []
    envelope: JsonDict | None = message_envelope(
        instance_id, str(payload["t"]), as_dict(payload.get("d"))
    )
    return [envelope] if envelope is not None else []
