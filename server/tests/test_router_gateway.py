"""Gateway end to end over HTTP: REST, MCP, console routes, QQ ingest and sending.

OneBot is faked at ``OneBotAdapter.call_action`` so the full chain runs: route ->
gateway -> outbox -> dispatcher thread -> shaper -> QQ provider -> recorded outcome.
"""

from __future__ import annotations

import sqlite3
import time
import types
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.gateway.impl import dispatch as dispatch_module
from hx_email.server.gateway.impl.breaker import BREAKER
from hx_email.server.gateway.listen import store_envelopes
from hx_email.server.gateway.providers import HUB, SHAPER
from hx_email.server.messaging.onebot import OneBotAdapter
from hx_email.server.messaging.registry import clear_runtime
from hx_email.server.router.providers.impl.github.github_auth import (
    GitHubAppConfig,
    seal_app_config,
)
from hx_email.server.router.providers.impl.qq_types import OneBotCallResult

API = "/api/v1"
SENT: list[tuple[str, dict[str, object]]] = []


def fake_call_action(
    self: OneBotAdapter, action: str, params: Mapping[str, object]
) -> OneBotCallResult:
    if action == "get_friend_list":
        return OneBotCallResult(
            transport="ok", http_status=200, data=[{"user_id": 10001, "nickname": "alice"}]
        )
    if action == "get_group_list":
        return OneBotCallResult(
            transport="ok", http_status=200, data=[{"group_id": 555, "group_name": "dev"}]
        )
    if action == "send_msg":
        SENT.append((action, dict(params)))
        return OneBotCallResult(
            transport="ok", http_status=200, data={"message_id": 9000 + len(SENT)}
        )
    return OneBotCallResult(transport="connect_error", wording="unreachable")


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    clear_runtime()
    HUB.clear()
    BREAKER.clear()
    SHAPER._buckets.clear()
    SHAPER._holds.clear()
    SENT.clear()
    monkeypatch.setattr(OneBotAdapter, "call_action", fake_call_action)
    monkeypatch.setattr(
        dispatch_module,
        "time",
        types.SimpleNamespace(sleep=lambda _s: None, monotonic=time.monotonic),
    )
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings), raise_server_exceptions=False)
    token = client.post(
        f"{API}/auth/login", json={"username": "admin", "password": "admin"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        f"{API}/messaging/instances",
        json={
            "kind": "qq",
            "name": "qq",
            "config": {"api_base_url": "http://127.0.0.1:9", "event_token": "tkn"},
        },
        headers=headers,
    )
    assert created.status_code == 201
    yield {
        "client": client,
        "headers": headers,
        "settings": settings,
        "qq": created.json()["instance"]["id"],
    }
    clear_runtime()
    HUB.clear()


def qq_event(message_id: int, text: str = "hello") -> dict[str, object]:
    return {
        "post_type": "message",
        "message_type": "group",
        "self_id": 2,
        "user_id": 10001,
        "group_id": 555,
        "message_id": message_id,
        "time": 1793632805,
        "sender": {"nickname": "alice"},
        "message": [{"type": "text", "data": {"text": text}}],
    }


def add_github(settings: Settings) -> int:
    config = GitHubAppConfig(
        "1",
        "Iv1",
        "slug",
        "-----BEGIN RSA PRIVATE KEY-----\nx\n-----END RSA PRIVATE KEY-----\n",
        "s",
    )
    with connect(settings) as connection:
        user_id = connection.execute("SELECT id FROM users LIMIT 1").fetchone()[0]
        cursor: sqlite3.Cursor = connection.execute(
            "INSERT INTO messaging_instances (user_id, kind, name, config_encrypted) "
            "VALUES (?, 'github', 'gh', ?)",
            (user_id, seal_app_config(settings, config)),
        )
        connection.commit()
        return int(cursor.lastrowid or 0)


def test_event_ingest_dedups_and_is_pullable(env: dict[str, Any]) -> None:
    client, headers, qq = env["client"], env["headers"], env["qq"]
    for _ in range(2):
        response = client.post(
            f"{API}/messaging/events/qq", json=qq_event(77), headers={"Authorization": "Bearer tkn"}
        )
        assert response.status_code == 200
    page = client.get(
        f"{API}/router/messages", params={"source": f"qq:{qq}:group:555"}, headers=headers
    ).json()
    assert [m["text"] for m in page["messages"]] == ["hello"]
    assert page["messages"][0]["session"] == f"qq:{qq}:group:555"
    legacy = client.get(
        f"{API}/messaging/instances/{qq}/messages",
        params={"chat_id": f"qq:{qq}:group:555"},
        headers=headers,
    )
    assert legacy.status_code == 200 and legacy.json()["messages"][0]["chat_id"] == "555"


def test_send_is_shaped_idempotent_and_recorded(env: dict[str, Any]) -> None:
    client, headers, qq = env["client"], env["headers"], env["qq"]
    body = {"sink": f"qq:{qq}:group:555", "text": "hi there", "idempotency_key": "key-00000001"}
    first = client.post(f"{API}/router/messages", json=body, headers=headers).json()
    assert first["status"] == "sent", first
    second = client.post(f"{API}/router/messages", json=body, headers=headers).json()
    assert second["deduplicated"] is True and second["delivery_id"] == first["delivery_id"]
    assert len(SENT) == 1
    status = client.get(f"{API}/router/deliveries/{first['delivery_id']}", headers=headers).json()
    assert status["platform_message_id"] == first["platform_message_id"]
    both = client.get(
        f"{API}/router/messages",
        params={"source": f"qq:{qq}:group:555", "direction": "both"},
        headers=headers,
    ).json()
    assert both["messages"][-1]["direction"] == "outbound"
    # a second message to the same session inside 3 s is queued, not sent
    queued = client.post(
        f"{API}/router/messages",
        json={**body, "idempotency_key": "key-00000002", "wait_seconds": 0},
        headers=headers,
    )
    assert queued.status_code == 202


def test_console_routes_no_longer_fail(env: dict[str, Any]) -> None:
    client, headers, qq, settings = env["client"], env["headers"], env["qq"], env["settings"]
    convs = client.get(f"{API}/messaging/instances/{qq}/conversations", headers=headers)
    assert convs.status_code == 200
    assert {c["session"] for c in convs.json()["conversations"]} >= {f"qq:{qq}:group:555"}
    sent = client.post(
        f"{API}/messaging/instances/{qq}/send",
        json={"chat_id": "555", "chat_type": "group", "text": "yo"},
        headers=headers,
    )
    assert sent.status_code == 200 and sent.json()["status"] == "sent"
    gh = add_github(settings)
    assert client.get(f"{API}/messaging/instances/{gh}", headers=headers).status_code == 200
    assert (
        client.get(f"{API}/messaging/instances/{gh}/conversations", headers=headers).status_code
        == 200
    )
    sources = client.get(f"{API}/router/sources", headers=headers).json()["sources"]
    assert {s["platform"] for s in sources} == {"qq", "github"}


def test_mcp_and_router_keys(env: dict[str, Any]) -> None:
    client, headers, qq = env["client"], env["headers"], env["qq"]
    issued = client.post(f"{API}/router/api-keys", json={"name": "ai"}, headers=headers).json()
    key_headers = {"Authorization": f"Bearer {issued['key']}"}
    assert client.post(f"{API}/router/api-keys", json={}, headers=key_headers).status_code == 403
    init = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        headers=key_headers,
    )
    assert init.json()["result"]["serverInfo"]["name"] == "hx-router"
    tools = client.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=key_headers
    ).json()
    assert "message_send" in {t["name"] for t in tools["result"]["tools"]}
    call = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "session_select", "arguments": {"session": f"qq:{qq}:group:555"}},
        },
        headers=key_headers,
    ).json()
    assert call["result"]["isError"] is False and call["result"]["structuredContent"][
        "cursor"
    ].startswith("c1.")
    bad = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "sources_list", "arguments": {"x": 1}},
        },
        headers=key_headers,
    ).json()
    assert bad["error"]["code"] == -32602
    foreign = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "sessions_list", "arguments": {"instance_id": 999}},
        },
        headers=key_headers,
    ).json()
    assert foreign["result"]["isError"] is True
    client.delete(f"{API}/router/api-keys/{issued['id']}", headers=headers)
    assert client.get(f"{API}/router/sources", headers=key_headers).status_code == 401


def test_wait_returns_on_new_message_and_hold_blocks_sending(env: dict[str, Any]) -> None:
    client, headers, qq = env["client"], env["headers"], env["qq"]
    timed_out = client.get(
        f"{API}/router/wait",
        params={"source": f"qq:{qq}:", "cursor": "", "timeout_seconds": 1},
        headers=headers,
    ).json()
    assert timed_out["timed_out"] is True
    client.post(
        f"{API}/messaging/events/qq",
        json=qq_event(88, "ping"),
        headers={"Authorization": "Bearer tkn"},
    )
    got = client.get(
        f"{API}/router/wait",
        params={"source": f"qq:{qq}:", "cursor": timed_out["next_cursor"], "timeout_seconds": 1},
        headers=headers,
    ).json()
    assert [m["text"] for m in got["messages"]] == ["ping"]
    assert (
        client.post(f"{API}/router/instances/{qq}/outbound/hold", headers=headers).json()[
            "outbound"
        ]
        == "manual_hold"
    )
    held = client.post(
        f"{API}/router/messages",
        json={"sink": f"qq:{qq}:group:555", "text": "x", "idempotency_key": "key-held-001"},
        headers=headers,
    ).json()
    assert held["status"] == "held" and SENT == []
    assert (
        client.post(f"{API}/router/instances/{qq}/outbound/resume", headers=headers).json()[
            "released"
        ]
        == 1
    )


def test_contract_v2_over_http(env: dict[str, Any]) -> None:
    client, headers, qq, settings = env["client"], env["headers"], env["qq"], env["settings"]
    caps = client.get(f"{API}/router/capabilities", headers=headers).json()
    assert caps["contract"] == 2
    assert {p["platform"] for p in caps["platforms"]} == {
        "qq",
        "github",
        "qqbot",
        "github_user",
    }
    client.post(
        f"{API}/messaging/events/qq", json=qq_event(91), headers={"Authorization": "Bearer tkn"}
    )
    page = client.get(
        f"{API}/router/messages", params={"source": f"qq:{qq}/group"}, headers=headers
    ).json()
    event = page["messages"][0]
    assert event["address"] == f"qq:{qq}/group/555" and event["kind"] == "message"
    assert event["session"] == f"qq:{qq}:group:555" and event["flags"]["from_self"] is False
    sent = client.post(
        f"{API}/router/messages",
        json={"sink": f"qq:{qq}/group/555", "text": "v2", "idempotency_key": "key-v2-0001"},
        headers=headers,
    ).json()
    assert sent["sink"] == f"qq:{qq}:group:555" and sent["address"] == f"qq:{qq}/group/555"
    gh = add_github(settings)
    store_envelopes(
        settings,
        gh,
        [
            {
                "session": f"github:{gh}:issue:hx/HX-Email#{number}",
                "sender": {"id": "5", "name": "u", "is_self": False},
                "text": f"t{number}",
                "platform_message_id": f"ic:{number}",
                "dedup_key": f"ic:{number}",
                "occurred_at": "2026-11-08T00:00:00Z",
            }
            for number in (1, 2)
        ]
        + [
            {
                "session": f"github:{gh}:issue:hx/Other#3",
                "sender": {"id": "5", "name": "u", "is_self": False},
                "text": "other",
                "platform_message_id": "ic:3",
                "dedup_key": "ic:3",
                "occurred_at": "2026-11-08T00:00:00Z",
            }
        ],
    )
    repo = client.get(
        f"{API}/router/messages",
        params={"source": f"github:{gh}/repo/hx/HX-Email"},
        headers=headers,
    ).json()
    assert [m["text"] for m in repo["messages"]] == ["t1", "t2"]
    assert repo["messages"][0]["kind"] == "comment"
    tool = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "capabilities_list", "arguments": {"platform": "qq"}},
        },
        headers=headers,
    ).json()
    platforms = tool["result"]["structuredContent"]["platforms"]
    assert [p["platform"] for p in platforms] == ["qq"]
