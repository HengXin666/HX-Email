"""GitHub 用户账号 (gh CLI): 子进程边界, setup 检查, notifications 轮询, observe, 出站动作.

全部用一个假的 gh 可执行脚本驱动: 它按路由表回 ``gh api --include`` 形状的输出, 并把每次调用
(参数, stdin, 环境) 记到 calls.jsonl, 测试据此断言请求与环境清理.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import stat
import sys
import time
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.contract.builtin import REGISTRY
from hx_email.server.contract.github_user.config import parse_config
from hx_email.server.gateway.impl import dispatch as dispatch_module
from hx_email.server.gateway.impl.breaker import BREAKER
from hx_email.server.gateway.impl.github_user_poll import AccountState, poll_account
from hx_email.server.gateway.providers import HUB, SHAPER, load_instance
from hx_email.server.messaging.registry import clear_runtime, creation_error
from hx_email.server.router.provider import ActionCall, OutboundPayload, SessionRef
from hx_email.server.router.providers.github_user import GitHubUserProvider
from hx_email.server.router.providers.impl.github_user.gh_cli import (
    CliFailedError,
    CliTimeoutError,
    GhCli,
    clean_env,
    split_include,
)
from hx_email.server.router.providers.impl.github_user.gh_setup import check_setup

API = "/api/v1"
REPO = "hx/HX-Email"
FAKE = r"""#!PYTHON
import json, os, sys, time
base = os.environ["FAKE_GH_DIR"]
args = sys.argv[1:]
stdin = sys.stdin.read() if "--input" in args else ""
with open(os.path.join(base, "calls.jsonl"), "a") as log:
    log.write(json.dumps({"args": args, "stdin": stdin, "env": dict(os.environ)}) + "\n")
method = args[args.index("--method") + 1] if "--method" in args else "GET"
valued = ("--method", "--hostname", "-H", "--input")
endpoint = [
    a for i, a in enumerate(args)
    if i > 0 and args[i - 1] not in valued and not a.startswith("-")
][-1]
headers = [args[i + 1] for i, a in enumerate(args) if a == "-H"]
routes_path = os.path.join(base, "routes.json")
routes = json.load(open(routes_path))
for index, route in enumerate(routes):
    match = route["match"]
    path = endpoint.split("?", 1)[0]
    hit = match in endpoint if ("?" in match or match.endswith("/")) else path.endswith(match)
    if route["method"] != method or not hit:
        continue
    if route.get("header") and route["header"] not in headers:
        continue
    if route.get("once"):
        routes.pop(index)
        json.dump(routes, open(routes_path, "w"))
    if route.get("sleep"):
        time.sleep(route["sleep"])
    if "stderr" in route:
        sys.stderr.write(route["stderr"])
        sys.exit(route.get("exit", 1))
    status = route.get("status", 200)
    sys.stdout.write("HTTP/2.0 %d X\n" % status)
    for name, value in route.get("headers", {}).items():
        sys.stdout.write("%s: %s\r\n" % (name, value))
    sys.stdout.write("\r\n")
    if "body" in route:
        sys.stdout.write(json.dumps(route["body"]))
    sys.exit(0 if status < 400 else 1)
sys.stderr.write("no route for %s %s" % (method, endpoint))
sys.exit(1)
"""


class FakeGh:
    def __init__(self, base: Path) -> None:
        self.base = base
        self.path = base / "gh-agent"
        self.path.write_text(FAKE.replace("#!PYTHON", "#!" + sys.executable))
        self.path.chmod(self.path.stat().st_mode | stat.S_IXUSR)
        self.routes: list[dict[str, Any]] = []
        self.save()

    def add(
        self, method: str, match: str, status: int = 200, body: Any = None, **extra: Any
    ) -> None:
        # 先读回文件: 子进程已消费掉的一次性路由不能被内存里的旧列表复活
        self.routes = json.loads((self.base / "routes.json").read_text())
        route: dict[str, Any] = {"method": method, "match": match, "status": status, **extra}
        if body is not None:
            route["body"] = body
        self.routes = [route, *self.routes] if extra.get("once") else [*self.routes, route]
        self.save()

    def save_empty(self) -> None:
        self.routes = []
        self.save()

    def save(self) -> None:
        (self.base / "routes.json").write_text(json.dumps(self.routes))

    def calls(self) -> list[dict[str, Any]]:
        log = self.base / "calls.jsonl"
        lines = log.read_text().splitlines() if log.exists() else []
        return [json.loads(line) for line in lines]

    def endpoints(self, method: str = "") -> list[str]:
        return [
            c["args"][-1] if "--input" not in c["args"] else c["args"][-3]
            for c in self.calls()
            if not method or c["args"][c["args"].index("--method") + 1] == method
        ]


@pytest.fixture()
def gh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeGh:
    monkeypatch.setenv("FAKE_GH_DIR", str(tmp_path))
    monkeypatch.setenv("GH_TOKEN", "should-not-leak")
    monkeypatch.setenv("GITHUB_TOKEN", "should-not-leak")
    monkeypatch.setenv("HX_EMAIL_SECRET_KEY", "should-not-leak")
    monkeypatch.setenv("MY_PASSWORD_FILE", "x")
    return FakeGh(tmp_path)


def user_ok(gh: FakeGh, push: bool = True) -> None:
    gh.add("GET", "user", body={"login": "hx-agent"}, headers={"X-OAuth-Scopes": "repo, read:org"})
    gh.add("GET", f"repos/{REPO}", body={"permissions": {"pull": True, "push": push}})


def test_clean_env_and_include_parsing() -> None:
    env = clean_env(
        {"HOME": "/h", "PATH": "/bin", "GH_TOKEN": "t", "GH_CONFIG_DIR": "/c", "API_KEY": "k"}
        | {"db_password": "p", "AWS_SECRET_ACCESS_KEY": "s", "GITHUB_TOKEN": "g"}
    )
    assert env["HOME"] == "/h" and env["PATH"] == "/bin" and env["GH_PROMPT_DISABLED"] == "1"
    assert not {"GH_TOKEN", "GH_CONFIG_DIR", "API_KEY", "db_password", "GITHUB_TOKEN"} & set(env)
    parsed = split_include(b'HTTP/2.0 201 Created\nLink: <x>; rel="next"\r\nA: b\r\n\r\n{"id": 1}')
    assert parsed is not None and parsed[0] == 201 and parsed[1]["link"] == '<x>; rel="next"'
    assert parsed[2] == b'{"id": 1}'
    assert split_include(b"HTTP/2.0 304 Not Modified\n\r\n") == (304, {}, b"")
    assert split_include(b"oops") is None


def test_setup_failures_and_success(gh: FakeGh, tmp_path: Path) -> None:
    def run(cli: str, repo: str = REPO) -> dict[str, Any]:
        return asyncio.run(check_setup({"cli": cli, "repository": repo})).to_dict()

    assert run("")["code"] == "cli_not_configured"
    assert run("gh-agent")["code"] == "cli_not_absolute"
    assert run(str(tmp_path / "missing"))["code"] == "cli_not_found"
    plain = tmp_path / "plain"
    plain.write_text("x")
    assert run(str(plain))["code"] == "cli_not_executable"
    assert run(str(gh.path), "nope")["code"] == "repository_invalid"
    gh.add("GET", "user", stderr="To get started with GitHub CLI, run: gh auth login", once=True)
    report = run(str(gh.path))
    assert report["code"] == "not_authenticated" and f"{gh.path} auth login" in report["hint"]
    gh.add("GET", "user", sleep=3, once=True)
    timed = asyncio.run(check_setup({"cli": str(gh.path), "repository": REPO}, timeout=0.5))
    assert timed.code == "cli_timeout" and str(gh.path) in timed.message
    gh.add("GET", "user", body={"login": "hx-agent"})
    gh.add("GET", f"repos/{REPO}", status=404, body={"message": "Not Found"}, once=True)
    assert run(str(gh.path))["code"] == "repo_not_visible"
    gh.add("GET", f"repos/{REPO}", body={"permissions": {"pull": False}}, once=True)
    assert run(str(gh.path))["code"] == "repo_no_read"
    gh.add("GET", f"repos/{REPO}", body={"permissions": {"pull": True, "push": False}}, once=True)
    assert run(str(gh.path))["code"] == "repo_no_push"
    gh.save_empty()
    user_ok(gh)
    ok = run(str(gh.path))
    assert ok["ok"] is True and ok["login"] == "hx-agent" and ok["missing_scopes"] == []
    leaked = [c["env"] for c in gh.calls() if {"GH_TOKEN", "GITHUB_TOKEN"} & set(c["env"])]
    assert leaked == []
    assert all("HX_EMAIL_SECRET_KEY" not in c["env"] for c in gh.calls())
    assert all("--hostname" in c["args"] and "github.com" in c["args"] for c in gh.calls())


def test_cli_timeout_and_failure_classes(gh: FakeGh) -> None:
    gh.add("POST", "issues/1/comments", sleep=3)
    with pytest.raises(CliTimeoutError, match="did not finish"):
        asyncio.run(GhCli(str(gh.path), 0.5).api("POST", f"repos/{REPO}/issues/1/comments", {}))
    gh.add("GET", "weird", stderr="segfault", exit=2)
    with pytest.raises(CliFailedError, match="gh-agent failed"):
        asyncio.run(GhCli(str(gh.path)).api("GET", "weird"))
    refused = asyncio.run(GhCli(str(gh.path)).api("GET", "https://example.com/x"))
    assert refused.status == 422


def ready(gh: FakeGh, **extra: str) -> Any:
    raw = {"cli": str(gh.path), "repository": REPO, "login": "hx-agent", **extra}
    return lambda _iid: parse_config(raw, "online")


def ref(address: str) -> SessionRef:
    parts = address.split(":", 3)
    return SessionRef(address, "github_user", 7, parts[2], parts[3], "")


def test_provider_outbound_actions(gh: FakeGh) -> None:
    provider = GitHubUserProvider(ready(gh), timeout=5)
    gh.add("POST", f"repos/{REPO}/issues/42/comments", status=201, body={"id": 555})
    sent = provider.send(
        ref(f"github_user:7:issue:{REPO}#42"), OutboundPayload("d_1", "hi", "", "")
    )
    assert sent.status == "sent" and sent.platform_message_id == "ic:555"
    posted = json.loads(gh.calls()[-1]["stdin"])
    assert posted["body"].startswith("hi") and "hx-router delivery=d_1" in posted["body"]
    gh.add("POST", f"repos/{REPO}/issues", status=201, body={"id": 9})
    opened = provider.send(ref(f"github_user:7:repo:{REPO}"), OutboundPayload("d_2", "b", "", "T"))
    assert opened.platform_message_id == "is:9"
    issue = ref(f"github_user:7:issue:{REPO}#42")
    gh.add("POST", "issues/comments/555/reactions", status=201, body={"id": 77})
    reacted = provider.invoke(
        issue, ActionCall("d_3", "reaction_add", {"content": "+1", "message_id": "ic:555"})
    )
    assert reacted.platform_message_id == "re:77"
    gh.add(
        "POST",
        "graphql",
        body={"data": {"repository": {"issueOrPullRequest": {"__typename": "PullRequest"}}}},
        once=True,
    )
    gh.add("POST", "pulls/42/reviews", status=200, body={"id": 31})
    review = provider.invoke(issue, ActionCall("d_4", "review_submit", {"event": "APPROVE"}))
    assert review.status == "sent" and review.platform_message_id == "rv:31"
    gh.add(
        "POST",
        "graphql",
        body={"data": {"createDiscussion": {"discussion": {"databaseId": 41}}}},
        once=True,
    )
    gh.add(
        "POST",
        "graphql",
        body={
            "data": {
                "repository": {
                    "id": "R_1",
                    "discussionCategories": {
                        "pageInfo": {"hasNextPage": False},
                        "nodes": [{"id": "C_1", "name": "General", "slug": "general"}],
                    },
                }
            }
        },
        once=True,
    )
    created = provider.invoke(
        ref(f"github_user:7:repo:{REPO}"),
        ActionCall("d_5", "discussion_create", {"title": "t", "body": "b", "category": "general"}),
    )
    assert created.platform_message_id == "dn:41", created
    gh.add(
        "POST",
        "graphql",
        body={"data": {"addDiscussionComment": {"comment": {"databaseId": 51}}}},
        once=True,
    )
    gh.add(
        "POST", "graphql", body={"data": {"repository": {"discussion": {"id": "D_1"}}}}, once=True
    )
    commented = provider.invoke(
        ref(f"github_user:7:discussion:{REPO}#3"),
        ActionCall("d_6", "discussion_comment_create", {"body": "c"}),
    )
    assert commented.platform_message_id == "dc:51", commented
    other = provider.send(
        ref("github_user:7:issue:other/repo#1"), OutboundPayload("d_7", "x", "", "")
    )
    assert other.status == "failed" and other.error_code == "not_found"


def test_provider_timeout_unknown_and_retry(gh: FakeGh) -> None:
    provider = GitHubUserProvider(ready(gh), timeout=0.5)
    gh.add("POST", "issues/42/comments", sleep=3)
    gh.add("POST", "issues/42/reactions", sleep=3)
    issue = ref(f"github_user:7:issue:{REPO}#42")
    unknown = provider.send(issue, OutboundPayload("d_1", "hi", "", ""))
    assert unknown.status == "unknown" and unknown.error_code == "delivery_unknown"
    assert str(gh.path) in unknown.error_message
    retry = provider.invoke(issue, ActionCall("d_2", "reaction_add", {"content": "heart"}))
    assert retry.status == "retry" and retry.error_code == "provider_timeout"
    gh.add(
        "POST",
        "issues/43/comments",
        status=403,
        body={"message": "API rate limit exceeded"},
        headers={"Retry-After": "30"},
    )
    limited = provider.send(
        ref(f"github_user:7:issue:{REPO}#43"), OutboundPayload("d_3", "x", "", "")
    )
    assert limited.status == "retry" and limited.retry_after_seconds == 30
    offline = GitHubUserProvider(
        lambda _iid: parse_config({"cli": str(gh.path), "repository": REPO})
    )
    held = offline.send(issue, OutboundPayload("d_4", "x", "", ""))
    assert held.status == "retry" and held.error_code == "provider_offline"


@pytest.fixture()
def env(gh: FakeGh, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    clear_runtime()
    HUB.clear()
    BREAKER.clear()
    SHAPER._buckets.clear()
    SHAPER._holds.clear()
    monkeypatch.setattr(
        dispatch_module,
        "time",
        types.SimpleNamespace(sleep=lambda _s: None, monotonic=time.monotonic),
    )
    settings = Settings(data_dir=tmp_path / "data", admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings), raise_server_exceptions=False)
    token = client.post(
        f"{API}/auth/login", json={"username": "admin", "password": "admin"}
    ).json()["access_token"]
    yield {
        "client": client,
        "headers": {"Authorization": f"Bearer {token}"},
        "settings": settings,
        "gh": gh,
    }
    clear_runtime()
    HUB.clear()


def test_save_check_and_actions_over_rest(env: dict[str, Any]) -> None:
    client, headers, gh = env["client"], env["headers"], env["gh"]
    assert creation_error("github_user", {"cli": str(gh.path)}) is not None
    refused = client.post(
        f"{API}/router/github_user/save", json={"cli": "gh", "repository": REPO}, headers=headers
    )
    assert refused.status_code == 400
    gh.add("GET", "user", stderr="run: gh auth login", once=True)
    failed = client.post(
        f"{API}/router/github_user/save",
        json={"cli": str(gh.path), "repository": REPO},
        headers=headers,
    ).json()
    assert (
        failed["report"]["code"] == "not_authenticated" and failed["instance"]["status"] == "error"
    )
    iid = failed["instance"]["id"]
    user_ok(gh)
    checked = client.post(
        f"{API}/router/github_user/check", json={"instance_id": iid}, headers=headers
    ).json()
    assert checked["report"]["ok"] is True and checked["instance"]["config"]["login"] == "hx-agent"
    assert checked["instance"]["status"] == "online"
    caps = client.get(
        f"{API}/router/capabilities", params={"platform": "github_user"}, headers=headers
    ).json()
    actions = {a["name"]: a for a in caps["platforms"][0]["actions"]}
    assert actions["comment_create"]["requires"] == ["repo"]
    assert actions["discussion_create"]["requires"] == ["repo"]
    gh.add("POST", "issues/42/comments", status=201, body={"id": 901})
    body = {
        "target": f"github_user:{iid}/repo/hx/HX-Email/issue/42",
        "action": "comment_create",
        "params": {"text": "在看"},
        "idempotency_key": "user-act-01",
    }
    sent = client.post(f"{API}/router/actions", json=body, headers=headers).json()
    assert sent["status"] == "sent" and sent["platform_message_id"] == "ic:901", sent
    client.put(
        f"{API}/messaging/instances/{iid}/config",
        json={"config": {"disabled_actions": "reaction_add"}},
        headers=headers,
    )
    off = client.post(
        f"{API}/router/actions",
        json={
            **body,
            "action": "reaction_add",
            "params": {"content": "+1"},
            "idempotency_key": "user-act-02",
        },
        headers=headers,
    )
    assert off.status_code == 422 and off.json()["error"]["code"] == "action_not_supported"
    sources = client.get(
        f"{API}/router/sources", params={"platform": "github_user"}, headers=headers
    ).json()
    assert sources["sources"][0]["account_id"] == "hx-agent"
    assert REGISTRY.get("github_user") is not None and REGISTRY.get("github") is not None


def notification(
    thread_id: str, reason: str, kind: str, url: str, latest: str, title: str = "t"
) -> dict[str, Any]:
    return {
        "id": thread_id,
        "reason": reason,
        "updated_at": "2026-11-09T10:00:00Z",
        "repository": {"id": 1, "full_name": REPO},
        "subject": {"type": kind, "title": title, "url": url, "latest_comment_url": latest},
    }


def make_instance(settings: Settings, gh: FakeGh, **extra: str) -> Any:
    config = {"cli": str(gh.path), "repository": REPO, "login": "hx-agent", **extra}
    with connect(settings) as connection:
        user_id = int(connection.execute("SELECT id FROM users LIMIT 1").fetchone()[0])
    from hx_email.server.messaging.store import create_instance, update_instance_status

    created = create_instance(settings, user_id, "github_user", "acct", config)
    update_instance_status(settings, created.id, "online")
    return load_instance(settings, created.id)


def stored(settings: Settings) -> list[sqlite3.Row]:
    with connect(settings) as connection:
        return connection.execute(
            "SELECT chat_id, message_id AS platform_message_id FROM messaging_messages ORDER BY id"
        ).fetchall()


def test_notifications_poll_304_interval_paging_and_mark_read(env: dict[str, Any]) -> None:
    settings, gh = env["settings"], env["gh"]
    instance = make_instance(settings, gh)
    api = f"https://api.github.com/repos/{REPO}"
    page1 = [
        notification("1", "mention", "Issue", f"{api}/issues/42", f"{api}/issues/comments/555"),
        notification("2", "subscribed", "Issue", f"{api}/issues/43", f"{api}/issues/comments/556"),
    ]
    page2 = [
        notification("3", "review_requested", "PullRequest", f"{api}/pulls/44", f"{api}/pulls/44")
    ]
    gh.add("GET", "notifications?per_page=50&page=2", body=page2)
    gh.add(
        "GET",
        "notifications?per_page=50",
        status=304,
        header="If-Modified-Since: Mon, 09 Nov 2026 10:00:00 GMT",
        headers={"X-Poll-Interval": "120"},
    )
    gh.add(
        "GET",
        "notifications?per_page=50",
        body=page1,
        headers={
            "Last-Modified": "Mon, 09 Nov 2026 10:00:00 GMT",
            "X-Poll-Interval": "90",
            "Link": f'<{api}/notifications?per_page=50&page=2>; rel="next"',
        },
    )
    gh.add(
        "GET",
        "issues/42",
        body={"id": 4200, "number": 42, "title": "bug", "user": {"login": "hx-agent"}},
    )
    gh.add(
        "GET",
        "issues/comments/555",
        body={
            "id": 555,
            "body": "@hx-agent 看下",
            "user": {"login": "alice", "type": "User"},
            "created_at": "2026-11-09T10:00:00Z",
        },
    )
    gh.add(
        "GET",
        "issues/44",
        body={
            "id": 4400,
            "number": 44,
            "title": "pr",
            "body": "x",
            "pull_request": {"url": "u"},
            "user": {"login": "bob"},
            "created_at": "2026-11-09T09:00:00Z",
        },
    )
    gh.add("PATCH", "notifications/threads/", status=205)
    state = AccountState()
    wait = asyncio.run(poll_account(settings, instance, state))
    assert wait == 90 and state.last_modified == "Mon, 09 Nov 2026 10:00:00 GMT"
    rows = stored(settings)
    assert [r["platform_message_id"] for r in rows] == ["ic:555", "pr:4400"]
    assert rows[0]["chat_id"] == f"github_user:{instance.id}:issue:{REPO}#42"
    assert sorted(gh.endpoints("PATCH")) == ["notifications/threads/1", "notifications/threads/3"]
    from hx_email.server.router.impl.reader import read_messages

    page = read_messages(
        settings, instance.user_id, f"github_user:{instance.id}", "", limit=10, include_raw=True
    )
    first = page.messages[0].to_dict(True)
    assert first["platform"] == "github_user"
    again = asyncio.run(poll_account(settings, instance, state))
    assert again == 120 and len(stored(settings)) == 2


def test_notification_flags_follow_login(env: dict[str, Any]) -> None:
    from hx_email.server.router.providers.impl.github.github_mapping import Draft, Thread
    from hx_email.server.router.providers.impl.github_user.gh_mapping import user_envelope

    thread = Thread("issue", f"{REPO}#1", "issue", {"login": "HX-Agent"})
    draft = Draft(
        thread,
        "comment",
        {"login": "alice"},
        {},
        "ping @hx-agent",
        "ic:1",
        "2026-11-09T10:00:00Z",
        {},
    )
    envelope = user_envelope(3, draft, "hx-agent")
    assert envelope["flags"] == {"from_self": False, "mention_self": True, "reply_to_self": True}
    mine = user_envelope(
        3,
        Draft(thread, "comment", {"login": "hx-agent"}, {}, "@hx-agent", "ic:2", "", {}),
        "hx-agent",
    )
    assert mine["flags"]["from_self"] is True and mine["flags"]["mention_self"] is False
    assert mine["session"] == f"github_user:3:issue:{REPO}#1"


def test_observe_switches_pull_incrementally(env: dict[str, Any]) -> None:
    settings, gh = env["settings"], env["gh"]
    instance = make_instance(settings, gh, observe_issues="1", observe_comments="1", observe_ci="1")
    gh.add("GET", "notifications?per_page=50", body=[])
    gh.add(
        "GET",
        "issues?state=all",
        body=[
            {
                "id": 1,
                "number": 5,
                "title": "new",
                "user": {"login": "a"},
                "created_at": "2026-11-09T10:00:01Z",
                "updated_at": "2026-11-09T10:00:01Z",
            },
            {
                "id": 2,
                "number": 6,
                "pull_request": {},
                "created_at": "2026-11-09T10:00:02Z",
                "updated_at": "2026-11-09T10:00:02Z",
            },
        ],
    )
    gh.add(
        "GET",
        "issues/comments?",
        body=[
            {
                "id": 7,
                "body": "c",
                "issue_url": f"https://api.github.com/repos/{REPO}/issues/5",
                "html_url": "h",
                "user": {"login": "a"},
                "created_at": "2026-11-09T10:00:03Z",
                "updated_at": "2026-11-09T10:00:03Z",
            }
        ],
    )
    gh.add("GET", "pulls/comments?", body=[])
    gh.add(
        "GET",
        "actions/runs",
        body={
            "workflow_runs": [
                {
                    "id": 99,
                    "name": "ci",
                    "conclusion": "success",
                    "head_sha": "abcdef1",
                    "head_branch": "main",
                    "updated_at": "2026-11-09T10:00:04Z",
                    "run_attempt": 1,
                }
            ]
        },
    )
    state = AccountState(since="2026-11-09T10:00:00Z")
    asyncio.run(poll_account(settings, instance, state))
    ids = [r["platform_message_id"] for r in stored(settings)]
    assert ids == ["is:1", "ic:7", "ci:99"]
    assert state.since == "2026-11-09T10:00:04Z"
    assert any("since=2026-11-09T10:00:00Z" in e for e in gh.endpoints("GET"))


def test_poll_error_backs_off(env: dict[str, Any]) -> None:
    settings, gh = env["settings"], env["gh"]
    instance = make_instance(settings, gh)
    gh.add("GET", "notifications", status=502, body={})
    state = AccountState(last_modified="old")
    assert asyncio.run(poll_account(settings, instance, state)) == 120
    assert asyncio.run(poll_account(settings, instance, state)) == 240
    assert state.last_modified == "old"
    assert os.environ.get("FAKE_GH_DIR")


def test_instance_detail_over_messaging_rest(env: dict[str, Any]) -> None:
    client, headers, gh = env["client"], env["headers"], env["gh"]
    user_ok(gh)
    saved = client.post(
        f"{API}/router/github_user/save",
        json={"cli": str(gh.path), "repository": REPO},
        headers=headers,
    ).json()
    iid = saved["instance"]["id"]
    client.put(
        f"{API}/messaging/instances/{iid}/config",
        json={"config": {"event_token": "leak-me", "observe_ci": "1"}},
        headers=headers,
    )
    detail = client.get(f"{API}/messaging/instances/{iid}", headers=headers)
    assert detail.status_code == 200, detail.text
    instance = detail.json()["instance"]
    assert instance["kind"] == "github_user" and instance["status"] == "online"
    assert instance["config"]["login"] == "hx-agent" and instance["config"]["repository"] == REPO
    assert instance["config"]["event_token"] == "***" and instance["config"]["observe_ci"] == "1"
    caps = instance["capabilities"]
    assert caps["risk_level"] == "official" and caps["supports_history"] is True
    assert caps["supports_qr_login"] is False
    listed = client.get(f"{API}/messaging/instances", headers=headers).json()["instances"]
    assert [item["id"] for item in listed] == [iid]
    assert client.get(f"{API}/messaging/instances/999", headers=headers).status_code == 404
    login = client.post(f"{API}/messaging/instances/{iid}/login", headers=headers)
    assert login.status_code == 400 and "not available yet" in login.json()["detail"]


def test_config_cli_change_rechecks(env: dict[str, Any], tmp_path: Path) -> None:
    client, headers, gh = env["client"], env["headers"], env["gh"]
    user_ok(gh)
    saved = client.post(
        f"{API}/router/github_user/save",
        json={"cli": str(gh.path), "repository": REPO},
        headers=headers,
    ).json()
    iid = saved["instance"]["id"]
    url = f"{API}/messaging/instances/{iid}/config"
    plain = client.put(url, json={"config": {"observe_ci": "1", "login": "x"}}, headers=headers)
    assert plain.status_code == 200 and "report" not in plain.json()
    assert plain.json()["instance"]["config"]["login"] == "hx-agent"
    relative = client.put(url, json={"config": {"cli": "gh"}}, headers=headers)
    assert relative.status_code == 400
    missing = client.put(
        url, json={"config": {"cli": str(tmp_path / "no-such-gh")}}, headers=headers
    ).json()
    assert missing["report"]["code"] == "cli_not_found"
    assert missing["instance"]["status"] == "error" and missing["instance"]["config"]["login"] == ""
    back = client.put(url, json={"config": {"cli": f" {gh.path} "}}, headers=headers).json()
    assert back["report"]["ok"] is True and back["instance"]["status"] == "online"
    assert back["instance"]["config"]["cli"] == str(gh.path)
    assert back["instance"]["config"]["observe_ci"] == "1"
