"""入站二: observe 开关打开时, 用 REST 按 ``since`` 增量分页拉取仓库动态.

notifications 只覆盖与本账号有关的线程; 想把整个仓库当作消息源时打开对应开关:

- ``observe_issues`` / ``observe_pulls``: ``GET /issues?state=all&sort=updated&since=`` (含 PR),
  新建的出一条 ``thread_opened``, 本窗口内关闭的出一条 ``thread_state``
- ``observe_comments``: ``GET /issues/comments`` 与 ``GET /pulls/comments`` (都带 ``since``),
  线程号取自评论里的 url, 不为每条评论再查一次 issue
- ``observe_ci``: ``GET /actions/runs?status=completed`` 第一页, 本窗口内结束的每次运行一条 ``ci``

每个列表逐页处理 (每页 50, 最多 10 页), 只保留本页; 返回本轮见到的最大 ``updated_at``, 作为下一轮
的 ``since``. ``since`` 是包含边界, 边界上的条目会重复出现, 靠存储去重.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Final

from hx_email.server.contract.github_user.config import GhUserConfig
from hx_email.server.router.providers.impl.github.github_events import MAPPERS, JsonDict
from hx_email.server.router.providers.impl.github.github_http import HttpResponse
from hx_email.server.router.providers.impl.github.github_mapping import (
    Draft,
    Thread,
    as_dict,
    text_of,
)
from hx_email.server.router.providers.impl.github_user.gh_cli import GhCli
from hx_email.server.router.providers.impl.github_user.gh_inbox import PollError, Sink
from hx_email.server.router.providers.impl.github_user.gh_mapping import (
    MAX_PAGES,
    PAGE_SIZE,
    as_list,
    next_page,
    number_of,
    user_envelope,
    with_origin,
)

ORIGIN: Final[str] = "observe"


async def pages(cli: GhCli, url: str) -> AsyncIterator[list[JsonDict]]:
    """Yield one page at a time; at most ``MAX_PAGES`` pages per list per round."""
    for _page in range(MAX_PAGES):
        response: HttpResponse = await cli.api("GET", url)
        if response.status != 200:
            raise PollError(url.split("?", 1)[0], response.status)
        yield as_list(response.body)
        url = next_page(response.headers)
        if not url:
            return


def thread_drafts(repo: str, item: JsonDict, since: str) -> list[Draft]:
    is_pr: bool = bool(item.get("pull_request"))
    event: str = "pull_request" if is_pr else "issues"
    key: str = "pull_request" if is_pr else "issue"
    repository: JsonDict = {"full_name": repo}
    drafts: list[Draft] = []
    if text_of(item.get("created_at")) >= since:
        drafts += MAPPERS[event](
            event, {"action": "opened", key: item, "repository": repository}, ORIGIN
        )
    closed_at: str = text_of(item.get("closed_at"))
    if closed_at and closed_at >= since:
        closed: JsonDict = {"action": "closed", key: item, "repository": repository}
        drafts += [
            with_origin(draft, {}, f"{draft.message_id}:closed:{closed_at}")
            for draft in MAPPERS[event](event, closed | {"sender": item.get("closed_by")}, ORIGIN)
        ]
    return drafts


def comment_drafts(repo: str, comment: JsonDict, since: str, review: bool) -> list[Draft]:
    parent_url: str = text_of(comment.get("pull_request_url" if review else "issue_url"))
    is_pr: bool = review or "/pull/" in text_of(comment.get("html_url"))
    thread: JsonDict = {"number": number_of(parent_url), "user": {}}
    if is_pr:
        thread["pull_request"] = {"url": parent_url}
    event: str = "pull_request_review_comment" if review else "issue_comment"
    payload: JsonDict = {
        "action": "created" if text_of(comment.get("created_at")) >= since else "edited",
        "pull_request" if review else "issue": thread,
        "comment": comment,
        "repository": {"full_name": repo},
        "sender": comment.get("user"),
    }
    return MAPPERS[event](event, payload, ORIGIN)


def run_draft(repo: str, run: JsonDict) -> Draft:
    sha: str = text_of(run.get("head_sha"))
    text: str = (
        f"CI {text_of(run.get('name'))}: {text_of(run.get('conclusion')) or 'completed'}"
        f" ({text_of(run.get('head_branch'))})"
    )
    return Draft(
        thread=Thread("commit", f"{repo}@{sha}", "commit", {}),
        kind="ci",
        user=as_dict(run.get("actor")) or {"id": "github-actions", "login": "github-actions"},
        item={},
        text=text,
        message_id=f"ci:{run.get('id')}",
        occurred_at=text_of(run.get("updated_at")),
        raw={"gh_event": "workflow_run", "html_url": text_of(run.get("html_url"))},
        dedup_key=f"ci:{run.get('id')}:{run.get('run_attempt')}",
    )


def wanted(config: GhUserConfig, item: JsonDict) -> bool:
    return config.observe_pulls if item.get("pull_request") else config.observe_issues


# 开关打开才拉: 按 since 增量分页, 一次只持有一页, 返回本轮见到的最大 updated_at 作为下一轮游标
async def observe_round(
    cli: GhCli, config: GhUserConfig, instance_id: int, since: str, sink: Sink
) -> tuple[int, str]:
    repo: str = config.repository
    base: str = f"repos/{repo}"
    query: str = f"sort=updated&direction=asc&since={since}&per_page={PAGE_SIZE}"
    newest: str = since
    stored: int = 0

    def keep(drafts: list[Draft], updated: str) -> None:
        nonlocal stored, newest
        if drafts:
            stored += sink([user_envelope(instance_id, d, config.login) for d in drafts])
        newest = max(newest, updated)

    if config.observe_issues or config.observe_pulls:
        async for page in pages(cli, f"{base}/issues?state=all&{query}"):
            for item in page:
                drafts = thread_drafts(repo, item, since) if wanted(config, item) else []
                keep(drafts, text_of(item.get("updated_at")))
    if config.observe_comments:
        for path, review in (("issues/comments", False), ("pulls/comments", True)):
            async for page in pages(cli, f"{base}/{path}?{query}"):
                for comment in page:
                    keep(
                        comment_drafts(repo, comment, since, review),
                        text_of(comment.get("updated_at")),
                    )
    if config.observe_ci:
        runs: HttpResponse = await cli.api(
            "GET", f"{base}/actions/runs?status=completed&per_page={PAGE_SIZE}"
        )
        if runs.status != 200:
            raise PollError("actions/runs", runs.status)
        for run in as_list(runs.as_dict().get("workflow_runs")):
            updated: str = text_of(run.get("updated_at"))
            keep([run_draft(repo, run)] if updated >= since else [], updated)
    return stored, newest
