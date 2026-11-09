"""把 GitHub 用户账号拉到的数据归一成与 App 完全相同的 envelope.

不另写一套映射: 拉到的 issue, 评论, discussion 被拼成 App webhook 的载荷形状, 交给 App 的
``MAPPERS`` 生成 ``Draft``, 再用 App 的 ``to_envelope`` 出 envelope. 这里只做三件 App 不需要的事:

- 平台前缀 ``github`` 换成 ``github_user`` (地址树相同, 存储键只差前缀)
- 身份判断: App 按 ``slug[bot]`` 与 ``performed_via_github_app`` 认自己, 用户账号按登录名认
  (``from_self``, ``mention_self``, ``reply_to_self``)
- 分页与轮询头: ``Link: rel="next"``, ``X-Poll-Interval``
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Final

from hx_email.server.router.providers.impl.github.github_events import AppIdentity, JsonDict
from hx_email.server.router.providers.impl.github.github_mapping import (
    Draft,
    as_dict,
    text_of,
    to_envelope,
)

PLATFORM: Final[str] = "github_user"
APP_PLATFORM: Final[str] = "github"
NEXT_LINK: Final[re.Pattern[str]] = re.compile(r'<([^>]+)>\s*;\s*rel="next"')
PAGE_SIZE: Final[int] = 50
MAX_PAGES: Final[int] = 10


def app_address(address: str) -> str:
    """``github_user:<iid>:...`` as the App-shaped ``github:<iid>:...`` the write code parses."""
    prefix: str = f"{PLATFORM}:"
    return f"{APP_PLATFORM}:{address[len(prefix) :]}" if address.startswith(prefix) else address


def user_address(address: str) -> str:
    prefix: str = f"{APP_PLATFORM}:"
    return f"{PLATFORM}:{address[len(prefix) :]}" if address.startswith(prefix) else address


def is_login(user: object, login: str) -> bool:
    name: str = text_of(as_dict(user).get("login"))
    return bool(login) and name.lower() == login.lower()


# 归一复用 App 的 MAPPERS 与 to_envelope, 只换平台前缀并按登录名重判三个自我信号
def user_envelope(instance_id: int, draft: Draft, login: str) -> JsonDict:
    envelope: JsonDict = to_envelope(instance_id, draft, AppIdentity("", login))
    flags: JsonDict = as_dict(envelope.get("flags"))
    from_self: bool = bool(flags.get("from_self")) or is_login(draft.user, login)
    mentions: object = envelope.get("mentions")
    mention_self: bool = any(
        bool(as_dict(item).get("is_self"))
        for item in (mentions if isinstance(mentions, list) else [])
    )
    envelope["platform"] = PLATFORM
    envelope["session"] = user_address(text_of(envelope.get("session")))
    sender: JsonDict = as_dict(envelope.get("sender"))
    # GraphQL 作者没有数字 id, 用登录名兜底, 保证 sender.id 非空
    sender_id: str = text_of(sender.get("id")) or text_of(sender.get("name"))
    envelope["sender"] = sender | {"id": sender_id, "is_self": from_self}
    envelope["flags"] = {
        "from_self": from_self,
        "mention_self": not from_self and mention_self,
        "reply_to_self": not from_self and is_login(draft.thread.author, login),
    }
    return envelope


def with_origin(draft: Draft, extra: JsonDict, dedup_key: str = "") -> Draft:
    """Tag a draft with where it came from (notification thread, observe pass)."""
    return replace(draft, raw=draft.raw | extra, dedup_key=dedup_key or draft.dedup_key)


def next_page(headers: dict[str, str]) -> str:
    match: re.Match[str] | None = NEXT_LINK.search(headers.get("link", ""))
    return match.group(1) if match else ""


def poll_interval(headers: dict[str, str]) -> int:
    text: str = headers.get("x-poll-interval", "").strip()
    return int(text) if text.isdigit() else 0


def number_of(url: str) -> int:
    """Trailing number of an API url (``.../issues/42``); 0 when there is none."""
    tail: str = url.rstrip("/").rsplit("/", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def repository_of(full_name: str, raw: object) -> JsonDict:
    return {"full_name": full_name, "id": as_dict(raw).get("id")}


def as_list(value: object) -> list[JsonDict]:
    return [as_dict(item) for item in value] if isinstance(value, list) else []
