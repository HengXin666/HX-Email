"""github_user 真实联调发现的问题的回归测试 (不依赖真实账号).

输入取自 gh 2.102.0 对 github.com 的真实输出 (去掉了无关响应头), 覆盖:
304 与 205 的 ``--include`` 形状, 422 的 ``errors[]`` 原因, 同名 discussion 的匹配,
楼中楼回复作为最新评论, 以及空未读列表的 200 不带 ``Last-Modified``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass

from hx_email.server.contract.github_user.actions import GITHUB_USER_ACTIONS
from hx_email.server.contract.github_user.config import parse_config
from hx_email.server.router.providers.impl.github.github_http import (
    HttpResponse,
    classify_response,
    github_detail,
)
from hx_email.server.router.providers.impl.github_user.gh_cli import CliOutput, GhCli, to_response
from hx_email.server.router.providers.impl.github_user.gh_inbox import (
    discussion_drafts,
    poll_inbox,
)
from hx_email.server.router.providers.impl.github_user.gh_mapping import (
    latest_comment,
    pick_discussion,
)

REPO = "owner/test-repo"
REAL_304 = (
    b"HTTP/2.0 304 Not Modified\nAccess-Control-Allow-Origin: *\r\n"
    b"Last-Modified: Sun, 25 Oct 2026 17:49:23 GMT\r\nX-Poll-Interval: 60\r\n"
    b"X-Ratelimit-Used: 10\r\nX-Xss-Protection: 0\r\n\r\n"
)
REAL_205 = (
    b"HTTP/2.0 205 Reset Content\nAccess-Control-Allow-Origin: *\r\nX-Ratelimit-Used: 3\r\n\r\n"
)
REAL_422 = (
    b"HTTP/2.0 422 Unprocessable Entity\nContent-Type: application/json\r\n\r\n"
    b'{"message":"Unprocessable Entity","errors":["Review Can not approve your own pull request"],'
    b'"status":"422"}'
)


def test_real_gh_include_shapes_for_304_205_422() -> None:
    not_modified = to_response("gh", CliOutput(1, REAL_304, "gh: HTTP 304"))
    assert not_modified.status == 304
    assert not_modified.headers["x-poll-interval"] == "60"
    assert to_response("gh", CliOutput(0, REAL_205, "")).status == 205
    rejected = to_response("gh", CliOutput(1, REAL_422, "gh: Unprocessable Entity (HTTP 422)"))
    result = classify_response(rejected, 0, "rv")
    assert result.status == "failed" and result.error_code == "unprocessable"
    assert "Can not approve your own pull request" in result.error_message


def test_terminal_errors_carry_github_reason_capped() -> None:
    gone = classify_response(HttpResponse(404, {}, {"message": "x is not configured"}), 0, "ic")
    assert gone.error_message == "repository or thread is gone: x is not configured"
    denied = classify_response(
        HttpResponse(403, {}, {"message": "Resource not accessible by personal access token"}),
        0,
        "ic",
    )
    assert denied.error_code == "permission_denied"
    assert "personal access token" in denied.error_message
    body: dict[str, object] = {
        "message": "Validation Failed",
        "errors": [{"code": "invalid", "field": "x"}, "y"],
    }
    assert github_detail(body) == "Validation Failed; invalid; y"
    assert len(github_detail({"message": "m" * 1000})) == 300
    plain = classify_response(HttpResponse(422, {}, {}), 0, "ic")
    assert plain.error_message == "GitHub rejected the payload as unprocessable"


def test_discussion_actions_need_only_repo_scope() -> None:
    wanted = {"discussion_create", "discussion_comment_create"}
    assert {spec.name: spec.requires for spec in GITHUB_USER_ACTIONS if spec.name in wanted} == {
        name: ("repo",) for name in wanted
    }


# 实测形状: B 是后建的同名 discussion (更新时间最新), 通知其实来自 A 里一条楼中楼回复
DISCUSSION_A: dict[str, object] = {
    "number": 18,
    "title": "same",
    "createdAt": "2026-11-09T15:39:00Z",
    "comments": {
        "nodes": [
            {
                "createdAt": "2026-11-09T15:39:20Z",
                "replies": {"nodes": [{"createdAt": "2026-11-09T15:39:41Z"}]},
            }
        ]
    },
}
DISCUSSION_B: dict[str, object] = {
    "number": 19,
    "title": "same",
    "createdAt": "2026-11-09T15:39:47Z",
    "comments": {"nodes": []},
}


def test_same_title_picks_activity_closest_to_notification() -> None:
    nodes = [DISCUSSION_B, DISCUSSION_A]
    assert pick_discussion(nodes, "same", "2026-11-09T15:39:41Z") is DISCUSSION_A
    assert pick_discussion(nodes, "same", "2026-11-09T15:39:47Z") is DISCUSSION_B
    assert pick_discussion(nodes, "other", "2026-11-09T15:39:41Z") is None
    assert pick_discussion([DISCUSSION_A], "same", "") is DISCUSSION_A
    newest = latest_comment(DISCUSSION_A)
    assert newest is not None and newest["createdAt"] == "2026-11-09T15:39:41Z"
    assert latest_comment(DISCUSSION_B) is None


@dataclass(frozen=True)
class ScriptedCli(GhCli):
    """Answers ``api`` from a script in call order and records each request."""

    script: tuple[HttpResponse, ...] = ()
    seen: list[tuple[str, str, dict[str, object]]] | None = None

    async def api(
        self,
        method: str,
        url: str,
        body: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        log: list[tuple[str, str, dict[str, object]]] = self.seen if self.seen is not None else []
        log.append((method, url, dict(body or {}) | dict(headers or {})))
        return self.script[len(log) - 1]


def test_discussion_notification_reads_the_reply_in_the_matched_discussion() -> None:
    reply: dict[str, object] = {
        "databaseId": 6,
        "body": "reply",
        "createdAt": "2026-11-09T15:39:41Z",
        "author": {"login": "someone"},
        "replyTo": {"databaseId": 5},
    }
    top: dict[str, object] = {
        "databaseId": 5,
        "body": "top",
        "createdAt": "2026-11-09T15:39:20Z",
        "author": {"login": "someone"},
        "replies": {"nodes": [reply]},
    }
    detail: dict[str, object] = {
        "databaseId": 1800,
        "number": 18,
        "title": "same",
        "body": "A",
        "url": "https://github.com/owner/test-repo/discussions/18",
        "createdAt": "2026-11-09T15:39:00Z",
        "author": {"login": "hx-agent"},
        "comments": {"nodes": [top]},
    }
    listing = {"data": {"repository": {"discussions": {"nodes": [DISCUSSION_B, DISCUSSION_A]}}}}
    seen: list[tuple[str, str, dict[str, object]]] = []
    cli = ScriptedCli(
        "gh",
        script=(
            HttpResponse(200, {}, listing),
            HttpResponse(200, {}, {"data": {"repository": {"discussion": detail}}}),
        ),
        seen=seen,
    )
    thread: dict[str, object] = {
        "updated_at": "2026-11-09T15:39:41Z",
        "subject": {"title": "same", "type": "Discussion"},
        "repository": {"id": 1},
    }
    drafts = asyncio.run(discussion_drafts(cli, REPO, thread, "nt:1"))
    assert [draft.message_id for draft in drafts] == ["dc:6"]
    assert drafts[0].thread.peer.endswith("#18")
    assert seen[1][2]["variables"] == {"owner": "owner", "name": "test-repo", "number": 18}
    assert "body" not in str(seen[0][2]["query"])


def test_empty_unread_list_keeps_previous_last_modified() -> None:
    config = parse_config({"cli": "/x/gh", "repository": REPO, "login": "hx-agent"}, "online")
    seen: list[tuple[str, str, dict[str, object]]] = []
    cli = ScriptedCli("gh", script=(HttpResponse(200, {"x-poll-interval": "60"}, []),), seen=seen)
    previous = "Sun, 25 Oct 2026 17:49:23 GMT"
    result = asyncio.run(poll_inbox(cli, config, 1, previous, lambda envelopes: len(envelopes)))
    assert result.last_modified == previous and result.poll_interval == 60
    assert seen[0][2] == {"If-Modified-Since": previous}
