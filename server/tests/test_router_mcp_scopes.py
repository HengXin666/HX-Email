"""API key scopes on MCP and REST, legacy key migration, and tool outputSchema (stage 7)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from hx_email.api.impl.mcp.session_table import TABLE
from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.access.scopes import LEGACY_SCOPES
from hx_email.server.gateway.api_keys import hash_key, verify_key_record
from hx_email.server.gateway.listen import store_envelopes

from tests import test_router_gateway as gateway
from tests.mcp_helpers import initialize, rpc, tool, validate
from tests.test_router_hub import group_message

env = gateway.env
API = gateway.API


@pytest.fixture(autouse=True)
def fresh_table() -> Iterator[None]:
    TABLE.clear()
    yield
    TABLE.clear()


def key_headers(client: Any, headers: dict[str, str], scopes: list[str] | None) -> dict[str, str]:
    body: dict[str, Any] = {"name": "k"}
    if scopes is not None:
        body["scopes"] = scopes
    issued = client.post(f"{API}/router/api-keys", json=body, headers=headers)
    assert issued.status_code == 201, issued.text
    return {"Authorization": f"Bearer {issued.json()['key']}"}


def test_read_only_key_is_limited_everywhere(env: dict[str, Any]) -> None:
    client, headers, qq = env["client"], env["headers"], env["qq"]
    reader = key_headers(client, headers, ["router:read", "mcp"])
    session = initialize(client, reader)
    names = {t["name"] for t in rpc(client, session, "tools/list")["result"]["tools"]}
    assert "messages_pull" in names and "resources" not in names
    assert not names & {"message_send", "action_invoke", "subscription_create"}
    denied = tool(
        client,
        session,
        "message_send",
        sink=f"qq:{qq}:group:555",
        text="x",
        idempotency_key="k-12345678",
    )
    assert denied["error"]["code"] == -32003
    assert denied["error"]["data"]["code"] == "insufficient_scope"
    assert denied["error"]["data"]["required_scope"] == "router:send"
    sub = rpc(client, session, "resources/subscribe", {"uri": "hx://router/capabilities"})
    assert sub["error"]["data"]["required_scope"] == "resources:subscribe"
    assert rpc(client, session, "resources/list")["result"]["resources"]
    rest = client.post(
        f"{API}/router/messages",
        json={"sink": f"qq:{qq}:group:555", "text": "x", "idempotency_key": "k-1"},
        headers=reader,
    )
    assert rest.status_code == 403 and rest.json()["error"]["code"] == "insufficient_scope"
    assert client.get(f"{API}/router/subscriptions", headers=reader).status_code == 403
    assert client.get(f"{API}/router/sources", headers=reader).status_code == 200


def test_rest_only_key_cannot_open_mcp(env: dict[str, Any]) -> None:
    client, headers = env["client"], env["headers"]
    rest_only = key_headers(client, headers, ["router:read"])
    reply = client.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"}, headers=rest_only
    )
    assert reply.status_code == 403 and reply.json()["error"]["code"] == "insufficient_scope"


def test_each_scope_allows_its_own_calls(env: dict[str, Any]) -> None:
    client, headers, qq = env["client"], env["headers"], env["qq"]
    sender = initialize(client, key_headers(client, headers, ["mcp", "router:send"]))
    sent = tool(
        client,
        sender,
        "message_send",
        sink=f"qq:{qq}:group:555",
        text="hi",
        idempotency_key="k-abcdefgh",
    )
    assert sent["result"]["isError"] is False
    assert tool(client, sender, "sources_list")["error"]["code"] == -32003
    actor = initialize(client, key_headers(client, headers, ["mcp", "router:actions"]))
    names = {t["name"] for t in rpc(client, actor, "tools/list")["result"]["tools"]}
    assert names == {"action_invoke"}
    subs = initialize(client, key_headers(client, headers, ["mcp", "subscriptions", "router:read"]))
    assert (
        tool(client, subs, "subscription_create", source=f"qq:{qq}/group")["result"]["isError"]
        is False
    )
    watcher = initialize(
        client, key_headers(client, headers, ["mcp", "router:read", "resources:subscribe"])
    )
    assert (
        rpc(client, watcher, "resources/subscribe", {"uri": f"hx://router/instances/{qq}"})[
            "result"
        ]
        == {}
    )
    denied = rpc(client, watcher, "resources/read", {"uri": "hx://router/subscriptions/1"})
    assert denied["error"]["code"] == -32003
    admin = initialize(client, key_headers(client, headers, ["admin"]))
    assert len(rpc(client, admin, "tools/list")["result"]["tools"]) == 13
    bad = client.post(f"{API}/router/api-keys", json={"scopes": ["root"]}, headers=headers)
    assert bad.status_code == 422


def test_default_and_patched_scopes(env: dict[str, Any]) -> None:
    client, headers = env["client"], env["headers"]
    issued = client.post(
        f"{API}/router/api-keys", json={"name": "old-script"}, headers=headers
    ).json()
    assert issued["scopes"] == list(LEGACY_SCOPES)
    patched = client.patch(
        f"{API}/router/api-keys/{issued['id']}", json={"scopes": ["router:read"]}, headers=headers
    )
    assert patched.json()["scopes"] == ["router:read"]
    listed = client.get(f"{API}/router/api-keys", headers=headers).json()["keys"]
    assert listed[0]["scopes"] == ["router:read"]
    key = {"Authorization": f"Bearer {issued['key']}"}
    assert (
        client.patch(
            f"{API}/router/api-keys/{issued['id']}", json={"scopes": ["admin"]}, headers=key
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"{API}/router/api-keys/999", json={"scopes": ["mcp"]}, headers=headers
        ).status_code
        == 404
    )
    catalogue = client.get(f"{API}/router/api-keys/scopes", headers=headers).json()
    assert "admin" in catalogue["scopes"] and "admin" not in catalogue["default"]


def test_legacy_key_rows_keep_their_capabilities(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    with connect(settings) as connection:
        connection.execute("ALTER TABLE router_api_keys DROP COLUMN scopes")
        user = connection.execute("SELECT id FROM users LIMIT 1").fetchone()
        connection.execute(
            "INSERT INTO router_api_keys (user_id, name, key_prefix, key_hash) VALUES (?, ?, ?, ?)",
            (user["id"], "legacy", "hxr_lega", hash_key("hxr_legacy-key")),
        )
        connection.commit()
    migrate(settings)
    record = verify_key_record(settings, "hxr_legacy-key")
    assert record is not None and record.scopes == frozenset(LEGACY_SCOPES)
    with connect(settings) as connection:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(router_api_keys)")}
    assert "scopes" in columns
    migrate(settings)  # 幂等


def test_every_tool_declares_and_meets_its_output_schema(env: dict[str, Any]) -> None:
    client, headers, qq, settings = env["client"], env["headers"], env["qq"], env["settings"]
    store_envelopes(settings, qq, [group_message(qq, 1, "hello")])
    session = initialize(client, headers)
    tools = {t["name"]: t for t in rpc(client, session, "tools/list")["result"]["tools"]}
    assert all("outputSchema" in t for t in tools.values())
    selected = tool(
        client, session, "session_select", session=f"qq:{qq}:group:555", **{"from": "earliest"}
    )
    cursor = selected["result"]["structuredContent"]["cursor"]
    sent = tool(
        client,
        session,
        "message_send",
        sink=f"qq:{qq}:group:555",
        text="yo",
        idempotency_key="k-schema01",
    )
    delivery_id = sent["result"]["structuredContent"]["delivery_id"]
    route = tool(client, session, "subscription_create", source=f"qq:{qq}/group")
    route_id = route["result"]["structuredContent"]["id"]
    calls: dict[str, dict[str, Any]] = {
        "capabilities_list": {},
        "sources_list": {},
        "sessions_list": {"instance_id": qq},
        "session_select": {"session": f"qq:{qq}:group:555"},
        "messages_pull": {"source": f"qq:{qq}:", "cursor": cursor},
        "events_wait": {"source": f"qq:{qq}:", "cursor": cursor, "timeout_seconds": 1},
        "message_send": {
            "sink": f"qq:{qq}:group:555",
            "text": "yo",
            "idempotency_key": "k-schema01",
        },
        "action_invoke": {
            "target": f"qq:{qq}:group:555",
            "action": "message_send",
            "params": {"text": "act"},
            "idempotency_key": "k-schema02",
        },
        "delivery_status": {"delivery_id": delivery_id},
        "subscriptions_list": {},
        "subscription_create": {"source": f"qq:{qq}/group/555"},
        "subscription_wait": {"subscription_id": route_id, "timeout_seconds": 0},
        "subscription_ack": {"subscription_id": route_id, "cursor": cursor},
    }
    assert set(calls) == set(tools)
    for name, arguments in calls.items():
        reply = tool(client, session, name, **arguments)["result"]
        assert reply["isError"] is False, (name, reply)
        validate(tools[name]["outputSchema"], reply["structuredContent"], name)
        assert reply["content"][0]["type"] == "text"
    failed = tool(client, session, "sessions_list", instance_id=999)["result"]
    assert failed["isError"] is True and "structuredContent" not in failed
    assert sqlite3.sqlite_version_info >= (3, 35)
