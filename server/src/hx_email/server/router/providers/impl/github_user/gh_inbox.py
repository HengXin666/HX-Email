"""入站一: 轮询本账号在所配置仓库上的 notifications, 归一后入库, 处理完的 thread 标为已读.

- 只请求 ``GET /repos/{owner}/{name}/notifications``, 别的仓库的通知从不读也从不标已读
- 第一页带 ``If-Modified-Since`` (上一轮的 ``Last-Modified``), 304 即无事可做, 不计入限额
- ``X-Poll-Interval`` 交还给轮询器, 下一轮不早于它
- 逐页处理 (每页 50 条, 最多 10 页), 只留待标已读的 thread id; 全部页处理完才统一标已读,
  避免边翻页边标已读让未读列表前移而漏掉条目
- 某个 thread 取详情失败: 不标已读, 也不推进 ``Last-Modified``, 下一轮整体重来; 重复入库靠
  ``(instance_id, dedup_key)`` 去重

开关全关时只处理涉及本账号的 reason (``DIRECT_REASONS``); 其余 reason 的 thread 保持未读, 留给
observe 开关的 REST 增量拉取. 编辑 issue 正文加上的 ``@`` GitHub 不发通知, 这里也就收不到.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from hx_email.server.contract.github_user.config import GhUserConfig
from hx_email.server.router.providers.impl.github.github_events import MAPPERS, JsonDict
from hx_email.server.router.providers.impl.github.github_http import HttpResponse
from hx_email.server.router.providers.impl.github.github_mapping import Draft, as_dict, text_of
from hx_email.server.router.providers.impl.github_user.gh_cli import GhCli
from hx_email.server.router.providers.impl.github_user.gh_mapping import (
    MAX_PAGES,
    PAGE_SIZE,
    as_list,
    next_page,
    number_of,
    poll_interval,
    repository_of,
    user_envelope,
    with_origin,
)

DIRECT_REASONS: Final[frozenset[str]] = frozenset(
    {"mention", "team_mention", "review_requested", "assign", "author"}
)
DISCUSSIONS_QUERY: Final[str] = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    discussions(first: 20, orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes {
        databaseId number title body url createdAt author { login }
        comments(last: 1) {
          nodes { databaseId body url createdAt author { login } replyTo { databaseId } }
        }
      }
    }
  }
}
"""
Sink = Callable[[list[JsonDict]], int]
Mapper = Callable[[str, JsonDict, str], list[Draft]]


class PollError(Exception):
    """GitHub answered something other than the page or item we asked for."""

    def __init__(self, what: str, status: int) -> None:
        super().__init__(f"{what}: HTTP {status}")
        self.status: int = status


@dataclass(frozen=True)
class InboxRound:
    stored: int
    marked: int
    not_modified: bool
    poll_interval: int
    last_modified: str


async def fetch(cli: GhCli, url: str) -> JsonDict:
    response: HttpResponse = await cli.api("GET", url)
    if response.status != 200:
        raise PollError(url, response.status)
    return response.as_dict()


def mappers() -> dict[str, Mapper]:
    return MAPPERS


async def issue_drafts(cli: GhCli, repo: str, thread: JsonDict, origin: str) -> list[Draft]:
    subject: JsonDict = as_dict(thread.get("subject"))
    number: int = number_of(text_of(subject.get("url")))
    if not number:
        return []
    issue: JsonDict = await fetch(cli, f"repos/{repo}/issues/{number}")
    repository: JsonDict = repository_of(repo, thread.get("repository"))
    latest: str = text_of(subject.get("latest_comment_url"))
    table: dict[str, Mapper] = mappers()
    for marker, event, key in (
        ("/issues/comments/", "issue_comment", "issue"),
        ("/pulls/comments/", "pull_request_review_comment", "pull_request"),
    ):
        if marker in latest:
            comment: JsonDict = await fetch(cli, latest)
            payload: JsonDict = {"action": "created", key: issue, "comment": comment}
            payload |= {"repository": repository, "sender": comment.get("user")}
            return table[event](event, payload, origin)
    event = "pull_request" if issue.get("pull_request") else "issues"
    key = "pull_request" if event == "pull_request" else "issue"
    opened: JsonDict = {"action": "opened", key: issue, "repository": repository}
    return table[event](event, opened, origin)


async def commit_drafts(cli: GhCli, repo: str, thread: JsonDict, origin: str) -> list[Draft]:
    latest: str = text_of(as_dict(thread.get("subject")).get("latest_comment_url"))
    if f"/repos/{repo}/comments/" not in latest:
        return []
    comment: JsonDict = await fetch(cli, latest)
    payload: JsonDict = {"action": "created", "comment": comment, "sender": comment.get("user")}
    payload["repository"] = repository_of(repo, thread.get("repository"))
    return mappers()["commit_comment"]("commit_comment", payload, origin)


def node_user(node: JsonDict) -> JsonDict:
    return {"login": text_of(as_dict(node.get("author")).get("login")), "type": "User"}


async def discussion_drafts(cli: GhCli, repo: str, thread: JsonDict, origin: str) -> list[Draft]:
    """Notifications carry no discussion number: match the title among recently updated ones."""
    owner, name = repo.split("/", 1)
    body: JsonDict = {"query": DISCUSSIONS_QUERY, "variables": {"owner": owner, "name": name}}
    response: HttpResponse = await cli.api("POST", "graphql", body)
    if response.status != 200 or response.as_dict().get("errors"):
        raise PollError("discussions lookup", response.status)
    nodes = as_list(
        as_dict(
            as_dict(as_dict(response.as_dict().get("data")).get("repository")).get("discussions")
        ).get("nodes")
    )
    title: str = text_of(as_dict(thread.get("subject")).get("title"))
    found: JsonDict | None = next((n for n in nodes if text_of(n.get("title")) == title), None)
    if found is None:
        return []
    discussion: JsonDict = {
        "id": found.get("databaseId"),
        "number": found.get("number"),
        "title": title,
        "body": found.get("body"),
        "html_url": found.get("url"),
        "created_at": found.get("createdAt"),
        "user": node_user(found),
    }
    repository: JsonDict = repository_of(repo, thread.get("repository"))
    latest: list[JsonDict] = as_list(as_dict(found.get("comments")).get("nodes"))
    if not latest:
        payload: JsonDict = {"action": "created", "discussion": discussion}
        return mappers()["discussion"]("discussion", payload | {"repository": repository}, origin)
    node: JsonDict = latest[-1]
    comment: JsonDict = {
        "id": node.get("databaseId"),
        "body": node.get("body"),
        "html_url": node.get("url"),
        "created_at": node.get("createdAt"),
        "user": node_user(node),
        "parent_id": as_dict(node.get("replyTo")).get("databaseId"),
    }
    payload = {"action": "created", "discussion": discussion, "comment": comment}
    payload["repository"] = repository
    return mappers()["discussion_comment"]("discussion_comment", payload, origin)


async def thread_envelopes(
    cli: GhCli, config: GhUserConfig, instance_id: int, thread: JsonDict
) -> list[JsonDict] | None:
    """Envelopes for one notification thread; ``None`` means "not ours, leave it unread"."""
    reason: str = text_of(thread.get("reason"))
    if reason not in DIRECT_REASONS:
        return None
    thread_id: str = text_of(thread.get("id"))
    origin: str = f"nt:{thread_id}"
    kind: str = text_of(as_dict(thread.get("subject")).get("type"))
    if kind in ("Issue", "PullRequest"):
        drafts: list[Draft] = await issue_drafts(cli, config.repository, thread, origin)
    elif kind == "Discussion":
        drafts = await discussion_drafts(cli, config.repository, thread, origin)
    elif kind == "Commit":
        drafts = await commit_drafts(cli, config.repository, thread, origin)
    else:
        drafts = []
    updated: str = text_of(thread.get("updated_at"))
    tagged: list[Draft] = [
        with_origin(
            draft,
            {"gh_reason": reason, "gh_notification": thread_id},
            # 线程本身 (被指派, 被请求 review) 每次通知各算一条, 评论按评论 id 去重
            f"{draft.message_id}:{reason}:{updated}" if draft.kind == "thread_opened" else "",
        )
        for draft in drafts
    ]
    return [user_envelope(instance_id, draft, config.login) for draft in tagged]


# 只读所配置仓库的通知: If-Modified-Since 省配额, 全部页处理完才统一标已读, 出错不推进 Last-Modified
async def poll_inbox(
    cli: GhCli, config: GhUserConfig, instance_id: int, last_modified: str, sink: Sink
) -> InboxRound:
    url: str = f"repos/{config.repository}/notifications?per_page={PAGE_SIZE}"
    headers: dict[str, str] = {"If-Modified-Since": last_modified} if last_modified else {}
    response: HttpResponse = await cli.api("GET", url, None, headers)
    interval: int = poll_interval(response.headers)
    if response.status == 304:
        return InboxRound(0, 0, True, interval, last_modified)
    if response.status != 200:
        raise PollError("notifications", response.status)
    fresh: str = response.headers.get("last-modified", "")
    stored: int = 0
    done: list[str] = []
    complete: bool = True
    for page in range(MAX_PAGES):
        for thread in as_list(response.body):
            try:
                envelopes: list[JsonDict] | None = await thread_envelopes(
                    cli, config, instance_id, thread
                )
            except PollError:
                complete = False
                continue
            if envelopes is None:
                continue
            stored += sink(envelopes) if envelopes else 0
            done.append(text_of(thread.get("id")))
        following: str = next_page(response.headers)
        if not following or page == MAX_PAGES - 1:
            complete = complete and not following
            break
        response = await cli.api("GET", following)
        if response.status != 200:
            complete = False
            break
    marked: int = 0
    for thread_id in done:
        answer: HttpResponse = await cli.api("PATCH", f"notifications/threads/{thread_id}")
        marked += 1 if answer.status in (200, 205) else 0
    return InboxRound(stored, marked, False, interval, fresh if complete else last_modified)
