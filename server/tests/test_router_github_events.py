"""GitHub 事件补全与触发判定: 新事件类型, kind, mentions, flags, 入库后的 Event v2 视图."""

from __future__ import annotations

import copy
from pathlib import Path

from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.contract.event import event_view
from hx_email.server.router.envelope import validate_inbound
from hx_email.server.router.impl.reader import read_messages
from hx_email.server.router.impl.store import store_inbound
from hx_email.server.router.providers.impl.github.github_events import AppIdentity, map_event
from hx_email.server.router.providers.impl.github.github_mapping import find_mentions, utc_z

IDENTITY = AppIdentity("1234", "hx-router")
REPO = {"id": 5, "full_name": "hx/HX-Email"}
ALICE = {"id": 11, "login": "alice", "type": "User"}
BOT = {"id": 99, "login": "hx-router[bot]", "type": "Bot"}
WHEN = "2026-11-08T12:00:00Z"


def comment(body: str, **extra: object) -> dict[str, object]:
    return {"id": 501, "body": body, "created_at": WHEN, "html_url": "u", "user": ALICE} | extra


def issue_comment(
    body: str, author: dict[str, object] = ALICE, comment_id: int = 501
) -> dict[str, object]:
    return {
        "action": "created",
        "installation": {"id": 9},
        "repository": REPO,
        "sender": ALICE,
        "issue": {"number": 42, "title": "bug", "user": author},
        "comment": comment(body, id=comment_id),
    }


def one(event: str, payload: dict[str, object], delivery: str = "d-1") -> dict[str, object]:
    envelopes = map_event(7, event, delivery, payload, IDENTITY).envelopes
    assert len(envelopes) == 1
    validate_inbound(envelopes[0], 7)
    return envelopes[0]


def test_mentions_skip_code_emails_and_repeats() -> None:
    text = (
        "@hx-router 看下 @Alice, 抄送 a@b.com `@nobody`\n```\n@ghost\n```\n@alice @hx-router[bot]"
    )
    assert find_mentions(text, IDENTITY) == [
        {"id": "", "name": "hx-router", "is_self": True},
        {"id": "", "name": "Alice", "is_self": False},
        {"id": "", "name": "hx-router[bot]", "is_self": True},
    ]
    assert utc_z("2026-11-08T20:00:00+08:00") == WHEN
    assert utc_z(WHEN) == WHEN


def test_issue_comment_mention_and_reply_to_self_thread() -> None:
    env = one("issue_comment", issue_comment("@hx-router 帮忙复现"))
    assert env["kind"] == "comment"
    assert env["flags"] == {"from_self": False, "mention_self": True, "reply_to_self": False}
    on_bot_thread = one("issue_comment", issue_comment("谢谢", author=BOT))
    assert on_bot_thread["flags"] == {
        "from_self": False,
        "mention_self": False,
        "reply_to_self": True,
    }
    edited = one("issue_comment", issue_comment("改了") | {"action": "edited"})
    assert edited["edit"] is True and edited["dedup_key"] == "ic:501"


def test_self_message_never_triggers() -> None:
    payload = issue_comment("@hx-router 自己提到自己\n\n<!-- hx-router delivery=d_3 -->")
    env = one("issue_comment", payload)
    assert env["sender"] == {"id": "11", "name": "alice", "is_self": True}
    assert env["flags"] == {"from_self": True, "mention_self": False, "reply_to_self": False}


def test_review_and_state_messages() -> None:
    review = {
        "action": "submitted",
        "repository": REPO,
        "pull_request": {"number": 12, "user": BOT},
        "review": {
            "id": 77,
            "state": "APPROVED",
            "body": "LGTM",
            "user": ALICE,
            "submitted_at": WHEN,
        },
    }
    env = one("pull_request_review", review)
    assert (env["kind"], env["text"], env["platform_message_id"]) == (
        "review",
        "approved\n\nLGTM",
        "rv:77",
    )
    assert env["flags"]["reply_to_self"] is True  # type: ignore[index]
    empty = copy.deepcopy(review)
    empty["review"] = {"id": 78, "state": "commented", "body": "", "user": ALICE}
    assert map_event(7, "pull_request_review", "d", empty, IDENTITY).envelopes == []

    closed = {
        "action": "closed",
        "repository": REPO,
        "sender": ALICE,
        "pull_request": {"id": 3, "number": 12, "merged": True, "updated_at": WHEN},
    }
    state = one("pull_request", closed, delivery="d-9")
    assert (state["kind"], state["text"]) == ("thread_state", "PR #12 closed (merged)")
    assert state["dedup_key"] == "pr:3:closed:d-9"
    outcome = map_event(7, "pull_request", "d-9", closed, IDENTITY)
    assert outcome.session_updates[0]["session"] == "github:7:issue:hx/HX-Email#12"
    issue = {
        "action": "closed",
        "repository": REPO,
        "sender": ALICE,
        "issue": {"id": 4, "number": 43, "state_reason": "not_planned", "closed_at": WHEN},
    }
    assert one("issues", issue)["text"] == "Issue #43 closed (not_planned)"
    ready = closed | {"action": "ready_for_review"}
    assert one("pull_request", ready)["text"] == "PR #12 ready for review"
    labeled = closed | {"action": "labeled"}
    assert map_event(7, "pull_request", "d", labeled, IDENTITY).envelopes == []


def test_discussion_and_commit_sessions() -> None:
    discussion = {
        "action": "created",
        "repository": REPO,
        "sender": ALICE,
        "discussion": {
            "id": 8,
            "number": 5,
            "title": "路线图",
            "body": "@hx-router 总结一下",
            "created_at": WHEN,
            "user": ALICE,
        },
    }
    opened = one("discussion", discussion)
    assert opened["session"] == "github:7:discussion:hx/HX-Email#5"
    assert opened["kind"] == "thread_opened" and opened["platform_message_id"] == "dn:8"
    assert opened["flags"]["mention_self"] is True  # type: ignore[index]
    reply = discussion | {"comment": comment("同意", id=9, parent_id=6)}
    env = one("discussion_comment", reply)
    assert (env["platform_message_id"], env["reply_to"]) == ("dc:9", "dc:6")

    sha = "0123456789abcdef0123456789abcdef01234567"
    commit_comment = {
        "action": "created",
        "repository": REPO,
        "sender": ALICE,
        "comment": comment("这行有问题", id=12, commit_id=sha, path="a.py", line=3),
    }
    env = one("commit_comment", commit_comment)
    assert env["session"] == f"github:7:commit:hx/HX-Email@{sha}"
    assert env["raw"]["path"] == "a.py"  # type: ignore[index]

    push = {
        "ref": "refs/heads/main",
        "repository": REPO,
        "sender": ALICE,
        "commits": [
            {
                "id": sha,
                "distinct": True,
                "message": "fix: @hx-router 看下",
                "timestamp": "2026-11-08T20:00:00+08:00",
                "url": "c",
                "author": {"username": "alice"},
            },
            {"id": "f" * 40, "distinct": False, "message": "dup", "timestamp": WHEN},
        ],
    }
    commits = map_event(7, "push", "d", push, IDENTITY).envelopes
    assert len(commits) == 1
    validate_inbound(commits[0], 7)
    assert commits[0]["kind"] == "commit" and commits[0]["occurred_at"] == WHEN
    assert commits[0]["dedup_key"] == f"cm:hx/HX-Email@{sha}"
    assert map_event(7, "push", "d", push | {"deleted": True}, IDENTITY).envelopes == []


def test_stored_trigger_drives_the_event_view(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    with connect(settings) as connection:
        connection.execute(
            "INSERT INTO messaging_instances (user_id, kind, name) VALUES (1, 'github', 'gh')"
        )
        connection.commit()
    pull = {"number": 12, "user": ALICE}
    bot_line = {
        "action": "created",
        "repository": REPO,
        "sender": BOT,
        "pull_request": pull,
        "comment": comment("建议改名", id=600, user=BOT),
    }
    reply = bot_line | {"sender": ALICE, "comment": comment("好的", id=601, in_reply_to_id=600)}
    mention = issue_comment("ping @hx-router")
    for event, payload in (
        ("pull_request_review_comment", bot_line),
        ("pull_request_review_comment", reply),
        ("issue_comment", mention),
    ):
        envelope = map_event(1, event, "d", payload, IDENTITY).envelopes[0]
        store_inbound(settings, validate_inbound(envelope, 1))
    page = read_messages(settings, 1, "github:1/repo/hx/HX-Email", "", limit=10)
    views = [event_view(item.to_dict()) for item in page.messages]
    assert [view["kind"] for view in views] == ["review_comment", "review_comment", "comment"]
    assert views[0]["flags"]["from_self"] is True  # type: ignore[index]
    assert views[1]["flags"]["reply_to_self"] is True  # type: ignore[index]
    assert views[2]["flags"]["mention_self"] is True  # type: ignore[index]
    assert views[2]["mentions"] == [{"id": "", "name": "hx-router", "is_self": True}]
    edited = issue_comment("不用了") | {"action": "edited"}
    changed = map_event(1, "issue_comment", "d", edited, IDENTITY).envelopes[0]
    store_inbound(settings, validate_inbound(changed, 1))
    again = read_messages(settings, 1, "github:1/repo/hx/HX-Email", "", limit=10).messages
    view = event_view(again[2].to_dict())
    assert view["text"] == "不用了" and view["flags"]["mention_self"] is False  # type: ignore[index]
    orphan = issue_comment("库里没有原评论", comment_id=777) | {"action": "edited"}
    lost = map_event(1, "issue_comment", "d", orphan, IDENTITY).envelopes[0]
    result = store_inbound(settings, validate_inbound(lost, 1))
    assert (result.stored, result.updated) == (False, False)
    page = read_messages(settings, 1, "github:1/repo/hx/HX-Email", "", limit=10)
    assert len(page.messages) == 3
