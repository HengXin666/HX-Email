"""MCP resources: list paging, templates, read, subscribe and list_changed (stage 7)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from hx_email.api.impl.mcp.session_table import TABLE
from hx_email.api.impl.mcp_resources import catalog
from hx_email.server.gateway.listen import store_envelopes

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


def read_json(client: Any, session: dict[str, str], uri: str) -> dict[str, Any]:
    reply = rpc(client, session, "resources/read", {"uri": uri})
    content = reply["result"]["contents"][0]
    assert content["uri"] == uri and content["mimeType"] == "application/json"
    return json.loads(content["text"])  # type: ignore[no-any-return]


def test_list_pages_and_templates(env: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    client, headers, qq = env["client"], env["headers"], env["qq"]
    client.post(
        f"{gateway.API}/router/subscriptions", json={"source": f"qq:{qq}/group"}, headers=headers
    )
    session = initialize(client, headers)
    monkeypatch.setattr(catalog, "PAGE_SIZE", 2)
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(5):
        params: dict[str, Any] = {"cursor": cursor} if cursor else {}
        page = rpc(client, session, "resources/list", params)["result"]
        seen.extend(item["uri"] for item in page["resources"])
        cursor = page.get("nextCursor")
        if cursor is None:
            break
    assert seen == [
        "hx://router/capabilities",
        "hx://router/sources",
        f"hx://router/instances/{qq}",
        "hx://router/subscriptions/1",
    ]
    bad = rpc(client, session, "resources/list", {"cursor": "zzz"})
    assert bad["error"]["code"] == -32602
    templates = rpc(client, session, "resources/templates/list")["result"]["resourceTemplates"]
    assert "hx://router/sessions/{session}/messages{?cursor,limit}" in {
        t["uriTemplate"] for t in templates
    }


def test_read_resources(env: dict[str, Any]) -> None:
    client, headers, qq, settings = env["client"], env["headers"], env["qq"], env["settings"]
    store_envelopes(settings, qq, [group_message(qq, n, f"m{n}") for n in range(1, 6)])
    session = initialize(client, headers)
    assert read_json(client, session, "hx://router/capabilities")["platforms"]
    instance = read_json(client, session, f"hx://router/instances/{qq}")
    assert instance["instance_id"] == qq and instance["cursor"].startswith("c1.")
    uri = f"hx://router/sessions/qq%3A{qq}%3Agroup%3A555/messages?limit=2"
    recent = read_json(client, session, uri)
    assert [m["text"] for m in recent["messages"]] == ["m4", "m5"]
    store_envelopes(settings, qq, [group_message(qq, 6, "m6")])
    after = read_json(
        client,
        session,
        f"hx://router/sessions/qq%3A{qq}%3Agroup%3A555/messages?cursor={recent['next_cursor']}",
    )
    assert [m["text"] for m in after["messages"]] == ["m6"]
    v2 = read_json(client, session, f"hx://router/sessions/qq:{qq}/group/555/messages?limit=1")
    assert [m["text"] for m in v2["messages"]] == ["m6"]
    for missing in ("hx://router/instances/999", "hx://router/nope", "https://x/y"):
        assert rpc(client, session, "resources/read", {"uri": missing})["error"]["code"] == -32002
    assert rpc(client, session, "resources/read", {})["error"]["code"] == -32602


def test_subscription_resource_and_list_changed(env: dict[str, Any]) -> None:
    client, headers, qq, settings = env["client"], env["headers"], env["qq"], env["settings"]
    session = initialize(client, headers)
    created: dict[str, Any] = {}

    def create() -> None:
        created.update(
            client.post(
                f"{gateway.API}/router/subscriptions",
                json={"source": f"qq:{qq}/group"},
                headers=headers,
            ).json()
        )

    _, _, text = read_stream(
        client,
        {**session, **SSE},
        until=lambda body: "notifications/resources/list_changed" in body,
        act=create,
    )
    assert "list_changed" in text
    uri = f"hx://router/subscriptions/{created['id']}"
    assert read_json(client, session, uri)["id"] == created["id"]
    assert rpc(client, session, "resources/subscribe", {"uri": uri})["result"] == {}
    _, _, pushed = read_stream(
        client,
        {**session, **SSE},
        until=lambda body: uri in body,
        act=lambda: store_envelopes(settings, qq, [group_message(qq, 1, "hi")]),
    )
    assert '"notifications/resources/updated"' in pushed
    delivery = rpc(client, session, "resources/subscribe", {"uri": "hx://router/deliveries/1"})
    assert delivery["error"]["code"] == -32602
