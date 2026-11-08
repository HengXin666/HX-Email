"""Hub and persistent subscriptions: targeted wake-ups, async waits, ack and resume."""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3
import threading
import time
from typing import Any

from hx_email.database import connect
from hx_email.server.gateway.listen import store_envelopes
from hx_email.server.hub.bus import BUS, Hit, like_to_regex, matcher_for, sync_waiter
from hx_email.server.hub.consume import route_stream, wait_source
from hx_email.server.hub.subscriptions import get_route
from hx_email.server.router.impl.reader import parse_source

from tests import test_router_gateway as gateway

API = "/api/v1"
env = gateway.env


def group_message(instance_id: int, number: int, text: str, peer: str = "555") -> dict[str, object]:
    return {
        "session": f"qq:{instance_id}:group:{peer}",
        "sender": {"id": "10001", "name": "alice", "is_self": False},
        "text": text,
        "platform_message_id": f"hub-{peer}-{number}",
        "dedup_key": f"hub-{peer}-{number}",
        "occurred_at": "2026-11-08T00:00:00Z",
    }


def test_like_pattern_matches_sql_semantics() -> None:
    pattern = like_to_regex("github:7:issue:o/r#%")
    assert pattern.match("github:7:issue:o/r#12")
    assert not pattern.match("github:7:issue:o/rx#12")
    assert like_to_regex("a\\_b").match("a_b") and not like_to_regex("a\\_b").match("axb")


def test_publish_wakes_only_matching_waiters() -> None:
    group = sync_waiter(matcher_for(parse_source("qq:3:group:"), [3], "inbound"))
    session = sync_waiter(matcher_for(parse_source("qq:3:group:555"), [3], "inbound"))
    other = sync_waiter(matcher_for(parse_source("qq:4:"), [4], "both"))
    for waiter in (group, session, other):
        BUS.register(waiter)
    try:
        woke = BUS.publish([Hit(3, "qq:3:group:777", "inbound")])
        assert woke == 1
        assert group.fired.is_set() and not session.fired.is_set() and not other.fired.is_set()
        assert BUS.publish([Hit(3, "qq:3:group:555", "outbound")]) == 0
    finally:
        for waiter in (group, session, other):
            BUS.unregister(waiter)


def test_async_wait_returns_on_publish_and_holds_no_thread(env: dict[str, Any]) -> None:
    settings, qq = env["settings"], env["qq"]
    with connect(settings) as connection:
        row: sqlite3.Row = connection.execute("SELECT id FROM users LIMIT 1").fetchone()
    user_id = int(row[0])

    def later() -> None:
        time.sleep(0.3)
        store_envelopes(settings, qq, [group_message(qq, 1, "wake")])

    async def scenario() -> dict[str, object]:
        threading.Thread(target=later, daemon=True).start()
        return await wait_source(settings, user_id, f"qq:{qq}/group", "", timeout_seconds=10)

    started = time.monotonic()
    page = asyncio.run(scenario())
    assert time.monotonic() - started < 5
    assert [m["text"] for m in page["messages"]] == ["wake"]  # type: ignore[union-attr]
    assert BUS.waiting() == 0


def test_subscription_lifecycle_over_rest(env: dict[str, Any]) -> None:
    client, headers, qq, settings = env["client"], env["headers"], env["qq"], env["settings"]
    store_envelopes(settings, qq, [group_message(qq, 1, "before")])
    created = client.post(
        f"{API}/router/subscriptions",
        json={"source": f"qq:{qq}/group", "name": "bot", "filter": {"contains": "ping"}},
        headers=headers,
    )
    assert created.status_code == 201
    route = created.json()
    assert route["address"] == f"qq:{qq}/group" and route["backlog"] == 0
    store_envelopes(settings, qq, [group_message(qq, 2, "noise"), group_message(qq, 3, "ping one")])
    got = client.get(
        f"{API}/router/subscriptions/{route['id']}/events",
        params={"timeout_seconds": 1},
        headers=headers,
    ).json()
    assert [m["text"] for m in got["messages"]] == ["ping one"]
    assert got["ack_cursor"] == route["ack_cursor"]
    listed = client.get(f"{API}/router/subscriptions", headers=headers).json()
    assert listed["subscriptions"][0]["backlog"] == 2
    acked = client.post(
        f"{API}/router/subscriptions/{route['id']}/ack",
        json={"cursor": got["next_cursor"]},
        headers=headers,
    ).json()
    assert acked["ack_cursor"] == got["next_cursor"]
    again = client.get(
        f"{API}/router/subscriptions/{route['id']}/events",
        params={"timeout_seconds": 0},
        headers=headers,
    ).json()
    assert again["messages"] == [] and again["timed_out"] is True
    paused = client.patch(
        f"{API}/router/subscriptions/{route['id']}", json={"status": "paused"}, headers=headers
    ).json()
    assert paused["status"] == "paused"
    assert (
        client.get(f"{API}/router/subscriptions/{route['id']}/stream", headers=headers).json()[
            "error"
        ]["code"]
        == "route_invalid"
    )
    assert client.delete(f"{API}/router/subscriptions/{route['id']}", headers=headers).json()[
        "deleted"
    ]
    missing = client.get(f"{API}/router/subscriptions/{route['id']}", headers=headers)
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "route_not_found"
    bad = client.post(
        f"{API}/router/subscriptions",
        json={"source": "qq:999/group"},
        headers=headers,
    )
    assert bad.status_code == 404


def test_subscription_tools_over_mcp(env: dict[str, Any]) -> None:
    client, headers, qq, settings = env["client"], env["headers"], env["qq"], env["settings"]

    def call(name: str, arguments: dict[str, object]) -> dict[str, Any]:
        reply = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
            headers=headers,
        ).json()
        return reply["result"]["structuredContent"]  # type: ignore[no-any-return]

    names = {
        tool["name"]
        for tool in client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=headers
        ).json()["result"]["tools"]
    }
    assert {"subscription_create", "subscription_wait", "subscription_ack"} <= names
    route = call("subscription_create", {"source": f"qq:{qq}/group/555"})
    store_envelopes(settings, qq, [group_message(qq, 9, "mcp hi")])
    page = call("subscription_wait", {"subscription_id": route["id"], "timeout_seconds": 1})
    assert [m["text"] for m in page["messages"]] == ["mcp hi"]
    acked = call(
        "subscription_ack", {"subscription_id": route["id"], "cursor": page["next_cursor"]}
    )
    assert acked["ack_cursor"] == page["next_cursor"]
    waited = call("events_wait", {"source": f"qq:{qq}:", "cursor": "", "timeout_seconds": 1})
    assert [m["text"] for m in waited["messages"]] == ["mcp hi"]
    stats = client.get(f"{API}/router/hub", headers=headers).json()
    assert stats["waiting"] == 0 and stats["published"] >= 1


def test_route_stream_frames_and_auto_ack(env: dict[str, Any]) -> None:
    client, headers, qq, settings = env["client"], env["headers"], env["qq"], env["settings"]
    route = client.post(
        f"{API}/router/subscriptions", json={"source": f"qq:{qq}/group"}, headers=headers
    ).json()
    store_envelopes(settings, qq, [group_message(qq, 4, "streamed")])
    with connect(settings) as connection:
        user_id = int(connection.execute("SELECT id FROM users LIMIT 1").fetchone()[0])
    loaded = get_route(settings, user_id, int(route["id"]))

    async def scenario() -> list[str]:
        frames = route_stream(settings, user_id, loaded, "", auto_ack=True)
        seen: list[str] = [await anext(frames), await anext(frames)]
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(anext(frames), timeout=0.5)
        await frames.aclose()  # type: ignore[attr-defined]
        return seen

    ready, data = asyncio.run(scenario())
    assert ready.startswith("event: ready") and '"streamed"' in data
    assert get_route(settings, user_id, int(route["id"])).ack_position > loaded.ack_position
    assert BUS.waiting() == 0
