"""QQ 空间说说列表 (``emotion_cgi_msglist_v6``) 到路由 envelope.

一条说说是一个会话 (``qq:<iid>:qzonepost:<主人>_<tid>``, v2 为
``qq:<iid>/qzone/<主人>/post/<tid>``), 说说本身与它下面的评论, 二级回复都是这个会话里的消息.
消息 id 带上回复时要用的定位信息, 发送侧不必再查库:

- 说说 ``qzp:<tid>``
- 评论 ``qzc:<tid>:<评论序号>:<评论者>``
- 二级回复 ``qzr:<tid>:<评论序号>:<回复序号>:<回复者>``

正文里的 ``@{uin:123,nick:某人,who:1}`` 换成 ``@某人`` 并记进 mentions.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from hx_email.server.router.providers.impl.qzone.qzone_contract import int_of

JsonDict = dict[str, object]
POST_TYPE: Final[str] = "qzonepost"
TID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9A-Za-z]+$")
AT_PATTERN: Final[re.Pattern[str]] = re.compile(r"@\{uin:(\d+),nick:([^,}]*)[^}]*\}")


@dataclass(frozen=True)
class Item:
    """说说, 评论或回复里本层需要的字段."""

    message_id: str
    kind: str
    uin: str
    name: str
    text: str
    created: int
    reply_to: str
    reply_to_self: bool


def as_dict(value: object) -> JsonDict:
    return {str(key): item for key, item in value.items()} if isinstance(value, Mapping) else {}


def as_list(value: object) -> list[JsonDict]:
    return [as_dict(item) for item in value] if isinstance(value, list) else []


def post_session(instance_id: int, owner: str, tid: str) -> str:
    return f"qq:{instance_id}:{POST_TYPE}:{owner}_{tid}"


def utc_from_unix(value: object) -> str:
    moment: datetime = datetime.fromtimestamp(max(int_of(value), 0), tz=UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def render_mentions(text: str, self_uin: str) -> tuple[str, list[JsonDict]]:
    """``@{uin:..,nick:..}`` 换成 ``@昵称``; 同一个人只记一次."""
    mentions: list[JsonDict] = []
    seen: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        uin, nick = match.group(1), match.group(2) or match.group(1)
        if uin not in seen:
            seen.add(uin)
            mentions.append({"id": uin, "name": nick, "is_self": uin == self_uin})
        return f"@{nick}"

    return AT_PATTERN.sub(replace, text), mentions


def post_text(post: JsonDict) -> str:
    """正文; 转发的说说把原文接在后面, 图片只留占位."""
    text: str = str(post.get("content") or "")
    forwarded: JsonDict = as_dict(post.get("rt_con"))
    if forwarded.get("content"):
        text = f"{text}\n// 转发: {forwarded['content']}".strip()
    pictures: int = len(as_list(post.get("pic")))
    return f"{text}\n[image x{pictures}]".strip() if pictures else text


def items_of(post: JsonDict, self_uin: str) -> list[Item]:
    """一条说说展开成说说本身, 评论与二级回复, 按出现顺序."""
    tid: str = str(post.get("tid") or "")
    owner: str = str(post.get("uin") or "")
    post_id: str = f"qzp:{tid}"
    found: list[Item] = [
        Item(
            post_id,
            "post",
            owner,
            str(post.get("name") or ""),
            post_text(post),
            int_of(post.get("created_time")),
            "",
            False,
        )
    ]
    for comment in as_list(post.get("commentlist")):
        ctid: str = str(int_of(comment.get("tid")))
        author: str = str(comment.get("uin") or "")
        comment_id: str = f"qzc:{tid}:{ctid}:{author}"
        found.append(
            Item(
                comment_id,
                "comment",
                author,
                str(comment.get("name") or ""),
                str(comment.get("content") or ""),
                int_of(comment.get("create_time")),
                post_id,
                owner == self_uin,
            )
        )
        for reply in as_list(comment.get("list_3")):
            rtid: str = str(int_of(reply.get("tid")))
            replier: str = str(reply.get("uin") or "")
            found.append(
                Item(
                    f"qzr:{tid}:{ctid}:{rtid}:{replier}",
                    "comment",
                    replier,
                    str(reply.get("name") or ""),
                    str(reply.get("content") or ""),
                    int_of(reply.get("create_time")),
                    comment_id,
                    author == self_uin,
                )
            )
    return found


# 说说, 评论与回复都由这里定 kind 与触发信号; 回复的是本号的说说或评论即 reply_to_self
# 决策记录: .agents/notes/implemented/feature/2026-11-09-qzone-provider.md
def feed_envelopes(instance_id: int, posts: list[JsonDict], self_uin: str) -> list[JsonDict]:
    """一页说说到 envelope 列表; tid 不合法的说说整条跳过."""
    envelopes: list[JsonDict] = []
    for post in posts:
        tid: str = str(post.get("tid") or "")
        owner: str = str(post.get("uin") or "")
        if not TID_PATTERN.match(tid) or not owner.isdigit():
            continue
        session: str = post_session(instance_id, owner, tid)
        for item in items_of(post, self_uin):
            text, mentions = render_mentions(item.text, self_uin)
            from_self: bool = item.uin == self_uin
            envelopes.append(
                {
                    "platform": "qq",
                    "instance_id": instance_id,
                    "session": session,
                    "session_type": POST_TYPE,
                    "chat_type": "group",
                    "direction": "inbound",
                    "sender": {"id": item.uin, "name": item.name, "is_self": from_self},
                    "text": text,
                    "reply_to": item.reply_to,
                    "platform_message_id": item.message_id,
                    "dedup_key": item.message_id,
                    "attachments": [],
                    "occurred_at": utc_from_unix(item.created),
                    "raw": {"qzone_owner": owner, "qzone_tid": tid, "qzone_kind": item.kind},
                    "kind": item.kind,
                    "mentions": mentions,
                    "flags": {
                        "from_self": from_self,
                        "mention_self": not from_self and any(m["is_self"] for m in mentions),
                        "reply_to_self": not from_self and item.reply_to_self,
                    },
                }
            )
    return envelopes


@dataclass(frozen=True)
class Target:
    """发送目标: 评论哪条说说, 或回复其中哪条评论."""

    owner: str
    tid: str
    comment_tid: str = ""
    comment_uin: str = ""


def reply_target(owner: str, tid: str, reply_to: str) -> Target:
    """``reply_to`` 是本说说下的评论或回复 id 时回复它所在的评论, 否则发一级评论."""
    parts: list[str] = reply_to.split(":")
    if len(parts) == 4 and parts[0] == "qzc" and parts[1] == tid:
        return Target(owner, tid, parts[2], parts[3])
    if len(parts) == 5 and parts[0] == "qzr" and parts[1] == tid:
        return Target(owner, tid, parts[2], parts[4])
    return Target(owner, tid)
