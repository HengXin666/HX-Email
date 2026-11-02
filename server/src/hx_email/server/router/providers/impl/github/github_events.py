"""GitHub webhook 入站: X-Hub-Signature-256 校验, 事件分发与 envelope 映射.

映射规则见 docs/providers/github-app.md 第 3 节与 docs/messaging-router.md 第 2, 3.4 节.
R3 任务范围: 只有 action 为 created 与 opened 的事件产出消息, 其它 action 只产出会话元数据.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass, field

SIGNATURE_HEADER: str = "x-hub-signature-256"
EVENT_HEADER: str = "x-github-event"
DELIVERY_HEADER: str = "x-github-delivery"
TARGET_ID_HEADER: str = "x-github-hook-installation-target-id"
SIGNATURE_PREFIX: str = "sha256="
MESSAGE_EVENTS: frozenset[str] = frozenset(
    {"issues", "issue_comment", "pull_request", "pull_request_review_comment"}
)
INSTALLATION_EVENTS: frozenset[str] = frozenset({"installation", "installation_repositories"})
HANDLED_EVENTS: frozenset[str] = MESSAGE_EVENTS | INSTALLATION_EVENTS
MESSAGE_ACTIONS: frozenset[str] = frozenset({"created", "opened"})
DELIVERY_MARKER: re.Pattern[str] = re.compile(r"\s*<!-- hx-router delivery=([^\s>]+) -->\s*$")
CHAT_TYPE_LEGACY: str = "group"

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


def strip_marker(text: str) -> tuple[str, str]:
    """去掉本 App 写入的隐藏标记, 返回 (正文, delivery_id 或空串)."""
    match: re.Match[str] | None = DELIVERY_MARKER.search(text)
    if match is None:
        return text, ""
    return text[: match.start()], match.group(1)


def as_dict(value: object) -> JsonDict:
    return value if isinstance(value, dict) else {}


def text_of(value: object) -> str:
    return value if isinstance(value, str) else ""


@dataclass(frozen=True)
class AppIdentity:
    app_id: str
    app_slug: str

    @property
    def bot_login(self) -> str:
        return f"{self.app_slug}[bot]"


@dataclass
class EventOutcome:
    envelopes: list[JsonDict] = field(default_factory=list)
    session_updates: list[JsonDict] = field(default_factory=list)
    installation_id: int | None = None
    repos_added: list[str] = field(default_factory=list)
    repos_removed: list[str] = field(default_factory=list)
    installation_removed: bool = False


def thread_session(instance_id: int, repo_full_name: str, number: object) -> str:
    return f"github:{instance_id}:issue:{repo_full_name}#{number}"


def is_self_sender(user: JsonDict, item: JsonDict, identity: AppIdentity, marker: str) -> bool:
    via_app: JsonDict = as_dict(item.get("performed_via_github_app"))
    if via_app and str(via_app.get("id", "")) == identity.app_id:
        return True
    if user.get("type") == "Bot" and user.get("login") == identity.bot_login:
        return True
    return marker != ""


def build_envelope(
    instance_id: int,
    session: str,
    user: JsonDict,
    item: JsonDict,
    text: str,
    message_id: str,
    occurred_at: str,
    raw: JsonDict,
    identity: AppIdentity,
    reply_to: str = "",
) -> JsonDict:
    clean, marker = strip_marker(text)
    return {
        "platform": "github",
        "instance_id": instance_id,
        "session": session,
        "session_type": "issue",
        "chat_type": CHAT_TYPE_LEGACY,
        "direction": "inbound",
        "sender": {
            "id": str(user.get("id", "")),
            "name": text_of(user.get("login")),
            "is_self": is_self_sender(user, item, identity, marker),
        },
        "text": clean,
        "reply_to": reply_to,
        "platform_message_id": message_id,
        "dedup_key": message_id,
        "attachments": [],
        "occurred_at": occurred_at,
        "raw": raw,
    }


def base_raw(event: str, payload: JsonDict, delivery: str, kind: str, html_url: str) -> JsonDict:
    return {
        "gh_event": event,
        "gh_action": text_of(payload.get("action")),
        "gh_delivery": delivery,
        "gh_installation_id": as_dict(payload.get("installation")).get("id"),
        "gh_repo_id": as_dict(payload.get("repository")).get("id"),
        "gh_thread_kind": kind,
        "html_url": html_url,
        "sender_type": text_of(as_dict(payload.get("sender")).get("type")),
    }


def map_comment(
    instance_id: int, event: str, payload: JsonDict, delivery: str, identity: AppIdentity
) -> JsonDict:
    repo: str = text_of(as_dict(payload.get("repository")).get("full_name"))
    comment: JsonDict = as_dict(payload.get("comment"))
    user: JsonDict = as_dict(comment.get("user"))
    if event == "issue_comment":
        issue: JsonDict = as_dict(payload.get("issue"))
        kind: str = "pull_request" if issue.get("pull_request") else "issue"
        session: str = thread_session(instance_id, repo, issue.get("number"))
        raw: JsonDict = base_raw(event, payload, delivery, kind, text_of(comment.get("html_url")))
        message_id: str = f"ic:{comment.get('id')}"
        reply_to: str = ""
    else:
        pull: JsonDict = as_dict(payload.get("pull_request"))
        session = thread_session(instance_id, repo, pull.get("number"))
        raw = base_raw(event, payload, delivery, "pull_request", text_of(comment.get("html_url")))
        raw["path"] = text_of(comment.get("path"))
        raw["line"] = comment.get("line")
        message_id = f"rc:{comment.get('id')}"
        parent: object = comment.get("in_reply_to_id")
        reply_to = f"rc:{parent}" if parent else ""
    return build_envelope(
        instance_id,
        session,
        user,
        comment,
        text_of(comment.get("body")),
        message_id,
        text_of(comment.get("created_at")),
        raw,
        identity,
        reply_to,
    )


def map_opened(
    instance_id: int, event: str, payload: JsonDict, delivery: str, identity: AppIdentity
) -> JsonDict:
    repo: str = text_of(as_dict(payload.get("repository")).get("full_name"))
    is_issue: bool = event == "issues"
    item: JsonDict = as_dict(payload.get("issue" if is_issue else "pull_request"))
    sender: JsonDict = as_dict(payload.get("sender"))
    title: str = text_of(item.get("title"))
    body: str = text_of(item.get("body"))
    text: str = f"{title}\n\n{body}" if body else title
    prefix: str = "is" if is_issue else "pr"
    kind: str = "issue" if is_issue else "pull_request"
    raw: JsonDict = base_raw(event, payload, delivery, kind, text_of(item.get("html_url")))
    return build_envelope(
        instance_id,
        thread_session(instance_id, repo, item.get("number")),
        sender,
        item,
        text,
        f"{prefix}:{item.get('id')}",
        text_of(item.get("created_at")),
        raw,
        identity,
    )


def session_update(instance_id: int, event: str, payload: JsonDict) -> JsonDict | None:
    """非 created/opened 的 action 只更新会话元数据 (标题, 状态), 不产消息."""
    repo: str = text_of(as_dict(payload.get("repository")).get("full_name"))
    key: str = "issue" if event in {"issues", "issue_comment"} else "pull_request"
    item: JsonDict = as_dict(payload.get(key))
    if not repo or "number" not in item:
        return None
    return {
        "session": thread_session(instance_id, repo, item.get("number")),
        "title": text_of(item.get("title")),
        "state": text_of(item.get("state")),
        "gh_action": text_of(payload.get("action")),
        "gh_thread_kind": "pull_request" if key == "pull_request" else "issue",
    }


def repo_names(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    return [text_of(as_dict(i).get("full_name")) for i in items if as_dict(i).get("full_name")]


def map_installation(event: str, payload: JsonDict, outcome: EventOutcome) -> None:
    action: str = text_of(payload.get("action"))
    if event == "installation":
        if action in {"deleted", "suspend"}:
            outcome.installation_removed = True
        else:
            outcome.repos_added = repo_names(payload.get("repositories"))
        return
    outcome.repos_added = repo_names(payload.get("repositories_added"))
    outcome.repos_removed = repo_names(payload.get("repositories_removed"))


def map_event(
    instance_id: int, event: str, delivery: str, payload: JsonDict, identity: AppIdentity
) -> EventOutcome:
    """事件分发: 未处理的事件返回空结果, 由调用方丢弃."""
    installation: object = as_dict(payload.get("installation")).get("id")
    outcome: EventOutcome = EventOutcome(
        installation_id=int(installation) if isinstance(installation, int) else None
    )
    if event in INSTALLATION_EVENTS:
        map_installation(event, payload, outcome)
        return outcome
    if event not in MESSAGE_EVENTS:
        return outcome
    action: str = text_of(payload.get("action"))
    if action not in MESSAGE_ACTIONS:
        update: JsonDict | None = session_update(instance_id, event, payload)
        if update is not None:
            outcome.session_updates.append(update)
        return outcome
    if event in {"issue_comment", "pull_request_review_comment"} and action == "created":
        outcome.envelopes.append(map_comment(instance_id, event, payload, delivery, identity))
    elif event in {"issues", "pull_request"} and action == "opened":
        outcome.envelopes.append(map_opened(instance_id, event, payload, delivery, identity))
    return outcome
