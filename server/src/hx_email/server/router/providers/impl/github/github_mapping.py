"""GitHub payloads to envelope dicts, one mapper per thread type, plus trigger signals.

Event table: docs/providers/github-app.md 3.1 and 3.3. Every envelope carries the trigger
fields a subscription filters on: ``kind``, ``mentions`` and ``flags`` (``from_self``,
``mention_self``, ``reply_to_self``), so they are stored with the row instead of being
guessed from the message id prefix at read time.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import UTC, datetime

DELIVERY_MARKER: re.Pattern[str] = re.compile(r"\s*<!-- hx-router delivery=([^\s>]+) -->\s*$")
# 代码块与行内代码里的 @ 不算提及; 前面紧跟字母数字, 点, 斜杠, @ 的是邮箱或路径
CODE_SPAN: re.Pattern[str] = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)
MENTION: re.Pattern[str] = re.compile(
    r"(?<![A-Za-z0-9_.@/`-])@([A-Za-z0-9](?:[A-Za-z0-9-]{0,38})(?:\[bot\])?)(?![A-Za-z0-9_/-])"
)
CHAT_TYPE_LEGACY: str = "group"
SIGNATURE_HEADER: str = "x-hub-signature-256"
EVENT_HEADER: str = "x-github-event"
DELIVERY_HEADER: str = "x-github-delivery"
TARGET_ID_HEADER: str = "x-github-hook-installation-target-id"
SIGNATURE_PREFIX: str = "sha256="

JsonDict = dict[str, object]


def verify_signature(secrets: tuple[bytes, ...], body: bytes, header_value: str | None) -> bool:
    """对原始 body 计算 HMAC-SHA256, 与请求头整体做常数时间比较; 任一 secret 匹配即通过."""
    if not secrets or not header_value or not header_value.startswith(SIGNATURE_PREFIX):
        return False
    matched: bool = False
    for secret in secrets:
        digest: str = hmac.new(secret, body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(SIGNATURE_PREFIX + digest, header_value):
            matched = True
    return matched


def sign_body(secret: bytes, body: bytes) -> str:
    return SIGNATURE_PREFIX + hmac.new(secret, body, hashlib.sha256).hexdigest()


def lower_headers(headers: dict[str, str]) -> dict[str, str]:
    return {key.lower(): value for key, value in headers.items()}


def as_dict(value: object) -> JsonDict:
    return value if isinstance(value, dict) else {}


def text_of(value: object) -> str:
    return value if isinstance(value, str) else ""


def strip_marker(text: str) -> tuple[str, str]:
    """去掉本 App 写入的隐藏标记, 返回 (正文, delivery_id 或空串)."""
    match: re.Match[str] | None = DELIVERY_MARKER.search(text)
    if match is None:
        return text, ""
    return text[: match.start()], match.group(1)


@dataclass(frozen=True)
class AppIdentity:
    app_id: str
    app_slug: str

    @property
    def bot_login(self) -> str:
        return f"{self.app_slug}[bot]"

    def is_me(self, login: str) -> bool:
        lowered: str = login.lower()
        return bool(self.app_slug) and lowered in {self.app_slug.lower(), self.bot_login.lower()}


@dataclass(frozen=True)
class Thread:
    """Where an event lands: ``kind`` is the v1 session type, ``peer`` its v1 peer."""

    kind: str
    peer: str
    gh_kind: str
    author: JsonDict

    def session(self, instance_id: int) -> str:
        return f"github:{instance_id}:{self.kind}:{self.peer}"


def is_self_user(user: JsonDict, item: JsonDict, identity: AppIdentity) -> bool:
    via_app: JsonDict = as_dict(item.get("performed_via_github_app"))
    if via_app and identity.app_id and str(via_app.get("id", "")) == identity.app_id:
        return True
    return user.get("type") == "Bot" and identity.is_me(text_of(user.get("login")))


def find_mentions(text: str, identity: AppIdentity) -> list[JsonDict]:
    """``@login`` outside code, in order, once each; ``is_self`` when it names this App."""
    seen: set[str] = set()
    found: list[JsonDict] = []
    for match in MENTION.finditer(CODE_SPAN.sub(" ", text)):
        login: str = match.group(1)
        if login.lower() in seen:
            continue
        seen.add(login.lower())
        found.append({"id": "", "name": login, "is_self": identity.is_me(login)})
    return found


def utc_z(value: str) -> str:
    """GitHub mostly sends ``...Z``; push commits carry an offset, normalise to UTC Z."""
    if not value or value.endswith("Z"):
        return value
    try:
        moment: datetime = datetime.fromisoformat(value)
    except ValueError:
        return value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Draft:
    """One message before it becomes an envelope dict."""

    thread: Thread
    kind: str
    user: JsonDict
    item: JsonDict
    text: str
    message_id: str
    occurred_at: str
    raw: JsonDict
    reply_to: str = ""
    dedup_key: str = ""
    edit: bool = False


def to_envelope(instance_id: int, draft: Draft, identity: AppIdentity) -> JsonDict:
    clean, marker = strip_marker(draft.text)
    from_self: bool = marker != "" or is_self_user(draft.user, draft.item, identity)
    mentions: list[JsonDict] = find_mentions(clean, identity)
    # 线程是本 App 开的, 线程里的每条都算回复本 App; 回复某条具体消息的, 由入库时按 reply_to 补判
    reply_to_self: bool = not from_self and is_self_user(draft.thread.author, {}, identity)
    envelope: JsonDict = {
        "platform": "github",
        "instance_id": instance_id,
        "session": draft.thread.session(instance_id),
        "session_type": draft.thread.kind,
        "chat_type": CHAT_TYPE_LEGACY,
        "direction": "inbound",
        "sender": {
            "id": str(draft.user.get("id", "")),
            "name": text_of(draft.user.get("login")) or text_of(draft.user.get("name")),
            "is_self": from_self,
        },
        "text": clean,
        "reply_to": draft.reply_to,
        "platform_message_id": draft.message_id,
        "dedup_key": draft.dedup_key or draft.message_id,
        "attachments": [],
        "occurred_at": utc_z(draft.occurred_at),
        "raw": draft.raw,
        "kind": draft.kind,
        "mentions": mentions,
        "flags": {
            "from_self": from_self,
            "mention_self": not from_self and any(m["is_self"] for m in mentions),
            "reply_to_self": reply_to_self,
        },
    }
    if draft.edit:
        envelope["edit"] = True
    return envelope


def base_raw(event: str, payload: JsonDict, delivery: str, gh_kind: str, url: str) -> JsonDict:
    return {
        "gh_event": event,
        "gh_action": text_of(payload.get("action")),
        "gh_delivery": delivery,
        "gh_installation_id": as_dict(payload.get("installation")).get("id"),
        "gh_repo_id": as_dict(payload.get("repository")).get("id"),
        "gh_thread_kind": gh_kind,
        "html_url": url,
        "sender_type": text_of(as_dict(payload.get("sender")).get("type")),
    }


def repo_of(payload: JsonDict) -> str:
    return text_of(as_dict(payload.get("repository")).get("full_name"))


def issue_thread(payload: JsonDict, key: str) -> Thread:
    item: JsonDict = as_dict(payload.get(key))
    is_pr: bool = key == "pull_request" or bool(item.get("pull_request"))
    return Thread(
        "issue",
        f"{repo_of(payload)}#{item.get('number')}",
        "pull_request" if is_pr else "issue",
        as_dict(item.get("user")),
    )


def discussion_thread(payload: JsonDict) -> Thread:
    item: JsonDict = as_dict(payload.get("discussion"))
    peer: str = f"{repo_of(payload)}#{item.get('number')}"
    return Thread("discussion", peer, "discussion", as_dict(item.get("user")))


def commit_thread(payload: JsonDict, sha: str) -> Thread:
    return Thread("commit", f"{repo_of(payload)}@{sha}", "commit", {})
