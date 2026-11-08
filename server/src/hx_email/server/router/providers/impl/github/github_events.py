"""GitHub webhook 入站: X-Hub-Signature-256 校验, 事件分发与 envelope 映射.

映射规则见 docs/providers/github-app.md 第 3 节与 docs/messaging-router.md 第 2, 3.4 节.
线程与触发信号的公共部分在 github_mapping.py, 这里只放签名, 安装事件与每类事件的取值.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from hx_email.server.router.providers.impl.github.github_mapping import (
    DELIVERY_HEADER,
    EVENT_HEADER,
    SIGNATURE_HEADER,
    TARGET_ID_HEADER,
    AppIdentity,
    Draft,
    JsonDict,
    as_dict,
    base_raw,
    commit_thread,
    discussion_thread,
    issue_thread,
    lower_headers,
    repo_of,
    sign_body,
    strip_marker,
    text_of,
    to_envelope,
    verify_signature,
)

__all__ = [
    "DELIVERY_HEADER",
    "EVENT_HEADER",
    "SIGNATURE_HEADER",
    "TARGET_ID_HEADER",
    "AppIdentity",
    "EventOutcome",
    "JsonDict",
    "lower_headers",
    "map_event",
    "sign_body",
    "strip_marker",
    "verify_signature",
]

INSTALLATION_EVENTS: frozenset[str] = frozenset({"installation", "installation_repositories"})
STATE_ACTIONS: frozenset[str] = frozenset({"closed", "reopened", "ready_for_review"})
# 推送里只取前 20 个提交: GitHub 的 push 载荷本身最多列 20 个
MAX_PUSH_COMMITS: int = 20

Mapper = Callable[[str, JsonDict, str], list[Draft]]


@dataclass
class EventOutcome:
    envelopes: list[JsonDict] = field(default_factory=list)
    session_updates: list[JsonDict] = field(default_factory=list)
    installation_id: int | None = None
    repos_added: list[str] = field(default_factory=list)
    repos_removed: list[str] = field(default_factory=list)
    installation_removed: bool = False


def comment_draft(
    event: str, payload: JsonDict, delivery: str, prefix: str, thread_key: str
) -> Draft:
    """issue_comment, pull_request_review_comment, discussion_comment, commit_comment."""
    comment: JsonDict = as_dict(payload.get("comment"))
    if thread_key == "discussion":
        thread = discussion_thread(payload)
    elif thread_key == "commit":
        thread = commit_thread(payload, text_of(comment.get("commit_id")))
    else:
        thread = issue_thread(payload, thread_key)
    url: str = text_of(comment.get("html_url"))
    raw: JsonDict = base_raw(event, payload, delivery, thread.gh_kind, url)
    if comment.get("path"):
        raw["path"] = text_of(comment.get("path"))
        raw["line"] = comment.get("line")
    parent: object = comment.get("in_reply_to_id") or comment.get("parent_id")
    return Draft(
        thread=thread,
        kind="review_comment" if prefix == "rc" else "comment",
        user=as_dict(comment.get("user")),
        item=comment,
        text=text_of(comment.get("body")),
        message_id=f"{prefix}:{comment.get('id')}",
        occurred_at=text_of(comment.get("created_at")),
        raw=raw,
        reply_to=f"{prefix}:{parent}" if parent else "",
        edit=text_of(payload.get("action")) == "edited",
    )


def comments(prefix: str, thread_key: str) -> Mapper:
    def mapper(event: str, payload: JsonDict, delivery: str) -> list[Draft]:
        if text_of(payload.get("action")) not in {"created", "edited"}:
            return []
        return [comment_draft(event, payload, delivery, prefix, thread_key)]

    return mapper


def state_text(event: str, action: str, item: JsonDict) -> str:
    label: str = "PR" if event == "pull_request" else "Issue"
    number: object = item.get("number")
    if action == "ready_for_review":
        return f"{label} #{number} ready for review"
    if action == "closed" and event == "pull_request":
        return f"{label} #{number} closed" + (" (merged)" if item.get("merged") else "")
    reason: str = text_of(item.get("state_reason"))
    suffix: str = f" ({reason})" if action == "closed" and reason else ""
    return f"{label} #{number} {action}{suffix}"


def threads(event: str, payload: JsonDict, delivery: str) -> list[Draft]:
    """issues, pull_request, discussion: opened is a message, closed and friends a state line."""
    action: str = text_of(payload.get("action"))
    key: str = "issue" if event == "issues" else event
    item: JsonDict = as_dict(payload.get(key))
    thread = discussion_thread(payload) if event == "discussion" else issue_thread(payload, key)
    prefix: str = {"issues": "is", "pull_request": "pr", "discussion": "dn"}[event]
    url: str = text_of(item.get("html_url"))
    raw: JsonDict = base_raw(event, payload, delivery, thread.gh_kind, url)
    message_id: str = f"{prefix}:{item.get('id')}"
    if action in {"opened", "created"}:
        title: str = text_of(item.get("title"))
        body: str = text_of(item.get("body"))
        return [
            Draft(
                thread=thread,
                kind="thread_opened",
                user=as_dict(item.get("user")) or as_dict(payload.get("sender")),
                item=item,
                text=f"{title}\n\n{body}" if body else title,
                message_id=message_id,
                occurred_at=text_of(item.get("created_at")),
                raw=raw,
            )
        ]
    if action not in STATE_ACTIONS or event == "discussion":
        return []
    return [
        Draft(
            thread=thread,
            kind="thread_state",
            user=as_dict(payload.get("sender")),
            item={},
            text=state_text(event, action, item),
            message_id=message_id,
            occurred_at=text_of(item.get("closed_at") or item.get("updated_at")),
            raw=raw,
            dedup_key=f"{message_id}:{action}:{delivery}",
        )
    ]


def reviews(event: str, payload: JsonDict, delivery: str) -> list[Draft]:
    """pull_request_review submitted; an empty "commented" review is only its line comments."""
    review: JsonDict = as_dict(payload.get("review"))
    state: str = text_of(review.get("state")).lower()
    body: str = text_of(review.get("body"))
    submitted: bool = text_of(payload.get("action")) == "submitted"
    if not submitted or not state or (state == "commented" and not body):
        return []
    thread = issue_thread(payload, "pull_request")
    return [
        Draft(
            thread=thread,
            kind="review",
            user=as_dict(review.get("user")),
            item=review,
            text=f"{state}\n\n{body}" if body else state,
            message_id=f"rv:{review.get('id')}",
            occurred_at=text_of(review.get("submitted_at")),
            raw=base_raw(event, payload, delivery, "pull_request", text_of(review.get("html_url"))),
        )
    ]


# push 的每个新提交是一条 commit 消息, 落在 commit 会话; 删分支与非 distinct 提交不产消息
# 决策记录: .agents/notes/implemented/feature/2026-11-08-github-events-triggers.md
def pushes(event: str, payload: JsonDict, delivery: str) -> list[Draft]:
    if payload.get("deleted"):
        return []
    raw: JsonDict = base_raw(event, payload, delivery, "commit", "")
    raw["ref"] = text_of(payload.get("ref"))
    sender: JsonDict = as_dict(payload.get("sender"))
    drafts: list[Draft] = []
    listed: object = payload.get("commits")
    for entry in (listed if isinstance(listed, list) else [])[:MAX_PUSH_COMMITS]:
        commit: JsonDict = as_dict(entry)
        sha: str = text_of(commit.get("id"))
        if not sha or commit.get("distinct") is False:
            continue
        author: JsonDict = as_dict(commit.get("author"))
        login: str = text_of(author.get("username"))
        user: JsonDict = sender if not login or login == sender.get("login") else {"login": login}
        drafts.append(
            Draft(
                thread=commit_thread(payload, sha),
                kind="commit",
                user=user,
                item={},
                text=text_of(commit.get("message")),
                message_id=f"cm:{sha}",
                occurred_at=text_of(commit.get("timestamp")),
                raw=raw | {"html_url": text_of(commit.get("url"))},
                dedup_key=f"cm:{repo_of(payload)}@{sha}",
            )
        )
    return drafts


MAPPERS: dict[str, Mapper] = {
    "issue_comment": comments("ic", "issue"),
    "pull_request_review_comment": comments("rc", "pull_request"),
    "discussion_comment": comments("dc", "discussion"),
    "commit_comment": comments("cc", "commit"),
    "pull_request_review": reviews,
    "issues": threads,
    "pull_request": threads,
    "discussion": threads,
    "push": pushes,
}
HANDLED_EVENTS: frozenset[str] = frozenset(MAPPERS) | INSTALLATION_EVENTS


def session_update(instance_id: int, event: str, payload: JsonDict) -> JsonDict | None:
    """线程的非新建 action 只更新会话元数据 (标题, 状态)."""
    if event == "discussion" or event.startswith("discussion_"):
        thread = discussion_thread(payload)
        item: JsonDict = as_dict(payload.get("discussion"))
    elif event in {"issues", "issue_comment"}:
        thread, item = issue_thread(payload, "issue"), as_dict(payload.get("issue"))
    elif event.startswith("pull_request"):
        thread, item = issue_thread(payload, "pull_request"), as_dict(payload.get("pull_request"))
    else:
        return None
    if not repo_of(payload) or "number" not in item:
        return None
    return {
        "session": thread.session(instance_id),
        "title": text_of(item.get("title")),
        "state": text_of(item.get("state")),
        "gh_action": text_of(payload.get("action")),
        "gh_thread_kind": thread.gh_kind,
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
    """事件分发: 未处理的事件与 action 返回空结果, 由调用方丢弃."""
    installation: object = as_dict(payload.get("installation")).get("id")
    outcome: EventOutcome = EventOutcome(
        installation_id=int(installation) if isinstance(installation, int) else None
    )
    if event in INSTALLATION_EVENTS:
        map_installation(event, payload, outcome)
        return outcome
    mapper: Mapper | None = MAPPERS.get(event)
    if mapper is None:
        return outcome
    drafts: list[Draft] = mapper(event, payload, delivery)
    outcome.envelopes = [to_envelope(instance_id, draft, identity) for draft in drafts]
    action: str = text_of(payload.get("action"))
    if action not in {"opened", "created"}:
        update: JsonDict | None = session_update(instance_id, event, payload)
        if update is not None:
            outcome.session_updates.append(update)
    return outcome
