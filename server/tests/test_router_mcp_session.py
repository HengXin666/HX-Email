"""MCP Streamable HTTP sessions and the GET SSE stream (stage 7)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from hx_email.api.impl.mcp import session_table, transport
from hx_email.api.impl.mcp.session_table import TABLE, McpSession, StreamSlot
from hx_email.server.gateway.listen import store_envelopes
from hx_email.server.hub.bus import BUS

from tests import test_router_gateway as gateway
from tests.mcp_helpers import initialize, read_stream, rpc
from tests.test_router_hub import group_message

env = gateway.env
SSE = {"Accept": "text/event-stream"}


@pytest.fixture(autouse=True)
def fresh_table() -> Iterator[None]:
    TABLE.clear()
    yield
    TABLE.clear()


def test_initialize_mints_session_and_requests_need_it(env: dict[str, Any]) -> None:
    client, headers = env["client"], env["headers"]
    init = client.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"}, headers=headers
    )
    result = init.json()["result"]
    assert result["capabilities"]["resources"] == {"subscribe": True, "listChanged": True}
    assert result["protocolVersion"] == "2025-06-18"
    session_id = init.headers["Mcp-Session-Id"]
    assert session_id and session_id.isascii()
    missing = client.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "ping"}, headers=headers
    )
    assert missing.status_code == 400
    unknown = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 3, "method": "ping"},
        headers={**headers, "Mcp-Session-Id": "nope"},
    )
    assert unknown.status_code == 404
    with_session = {**headers, "Mcp-Session-Id": session_id}
    assert rpc(client, with_session, "ping")["result"] == {}
    note = client.post(
        "/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=with_session
    )
    assert note.status_code == 202
    bad_version = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 4, "method": "ping"},
        headers={**with_session, "MCP-Protocol-Version": "1999-01-01"},
    )
    assert bad_version.status_code == 400
    old = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 5,
            "method": "initialize",
            "params": {"protocolVersion": "2025-03-26"},
        },
        headers=headers,
    )
    assert old.json()["result"]["protocolVersion"] == "2025-03-26"


def test_session_is_bound_to_its_credential(env: dict[str, Any]) -> None:
    client, headers = env["client"], env["headers"]
    session = initialize(client, headers)
    issued = client.post(f"{gateway.API}/router/api-keys", json={"name": "k"}, headers=headers)
    foreign = {
        "Authorization": f"Bearer {issued.json()['key']}",
        "Mcp-Session-Id": session["Mcp-Session-Id"],
    }
    assert (
        client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers=foreign
        ).status_code
        == 404
    )


def test_expiry_delete_and_limits(env: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    client, headers = env["client"], env["headers"]
    session = initialize(client, headers)
    stored: McpSession = TABLE.sessions[session["Mcp-Session-Id"]]
    stored.last_seen -= session_table.IDLE_SECONDS + 1
    assert (
        client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers=session
        ).status_code
        == 404
    )
    assert TABLE.count() == 0
    session = initialize(client, headers)
    assert client.delete("/mcp", headers=session).status_code == 204
    assert client.delete("/mcp", headers=session).status_code == 404
    assert client.delete("/mcp", headers=headers).status_code == 400
    first = initialize(client, headers)
    for _ in range(session_table.MAX_PER_PRINCIPAL):
        initialize(client, headers)
    assert TABLE.count() == session_table.MAX_PER_PRINCIPAL
    assert (
        client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers=first
        ).status_code
        == 404
    )
    monkeypatch.setattr(session_table, "MAX_SESSIONS", TABLE.count())
    other = client.post(
        f"{gateway.API}/router/api-keys", json={"name": "x"}, headers=headers
    ).json()
    full = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        headers={"Authorization": f"Bearer {other['key']}"},
    )
    assert full.status_code == 503


def test_get_stream_requires_session_and_accept(env: dict[str, Any]) -> None:
    client, headers = env["client"], env["headers"]
    first = client.get("/mcp", headers={**headers, **SSE})
    assert first.status_code == 400, first.text
    assert client.get("/mcp", headers={**headers, **SSE, "Mcp-Session-Id": "x"}).status_code == 404
    session = initialize(client, headers)
    assert client.get("/mcp", headers=session).status_code == 406


def test_stream_delivers_resumes_and_cleans_up(env: dict[str, Any]) -> None:
    client, headers, qq, settings = env["client"], env["headers"], env["qq"], env["settings"]
    session = initialize(client, headers)
    uri = f"hx://router/sessions/qq%3A{qq}%3Agroup%3A555/messages"
    baseline = BUS.waiting()
    assert rpc(client, session, "resources/subscribe", {"uri": uri})["result"] == {}
    assert BUS.waiting() == baseline + 1
    status, head, text = read_stream(
        client,
        {**session, **SSE},
        until=lambda body: "notifications/resources/updated" in body,
        act=lambda: store_envelopes(settings, qq, [group_message(qq, 1, "one")]),
    )
    assert status == 200 and head["content-type"].startswith("text/event-stream")
    assert "id: 1\n" in text and uri in text
    stored: McpSession = TABLE.sessions[session["Mcp-Session-Id"]]
    assert stored.stream is None  # 断开后槽位已清
    store_envelopes(settings, qq, [group_message(qq, 2, "two")])
    store_envelopes(settings, qq, [group_message(qq, 3, "three")])  # 同一 URI 合并
    _, _, resumed = read_stream(
        client, {**session, **SSE, "Last-Event-ID": "1"}, until=lambda body: "id: 2\n" in body
    )
    assert "id: 2\n" in resumed and "id: 3\n" not in resumed
    assert rpc(client, session, "resources/unsubscribe", {"uri": uri})["result"] == {}
    assert BUS.waiting() == baseline
    rpc(client, session, "resources/subscribe", {"uri": uri})
    assert client.delete("/mcp", headers=session).status_code == 204
    assert BUS.waiting() == baseline


def test_nothing_is_buffered_before_a_stream_opens(env: dict[str, Any]) -> None:
    client, headers, qq, settings = env["client"], env["headers"], env["qq"], env["settings"]
    session = initialize(client, headers)
    rpc(client, session, "resources/subscribe", {"uri": f"hx://router/instances/{qq}"})
    store_envelopes(settings, qq, [group_message(qq, 7, "early")])
    stored: McpSession = TABLE.sessions[session["Mcp-Session-Id"]]
    assert stored.seq == 0 and not stored.ring


def test_heartbeat_and_newer_stream_replaces_older(
    env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, headers = env["client"], env["headers"]
    monkeypatch.setattr(transport, "HEARTBEAT_SECONDS", 0.05)
    session = initialize(client, headers)
    _, _, text = read_stream(client, {**session, **SSE}, until=lambda body: ": ping" in body)
    assert ": ping" in text
    stored: McpSession = TABLE.sessions[session["Mcp-Session-Id"]]

    async def two_streams() -> bool:
        loop = asyncio.get_running_loop()
        older = StreamSlot(loop, asyncio.Event())
        stored.attach(older, None)
        stored.attach(StreamSlot(loop, asyncio.Event()), None)
        return older.closed

    assert asyncio.run(two_streams()) is True
    stored.ring.clear()
    for number in range(session_table.RING_SIZE + 10):
        stored.emit({"jsonrpc": "2.0", "method": "x", "params": {"n": number}})
    assert len(stored.ring) == session_table.RING_SIZE
