"""Push transports: webhook feed, signed delivery, retry ladder, and the WebSocket feed."""

from __future__ import annotations

import json
import random
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hx_email.database import connect
from hx_email.server.gateway.impl.dispatch import DISPATCHER
from hx_email.server.gateway.listen import store_envelopes
from hx_email.server.hub.bus import BUS
from hx_email.server.push import webhook_deliver
from hx_email.server.push.webhook_feed import FEEDER
from hx_email.server.push.webhook_target import (
    WebhookTarget,
    check_url,
    open_target,
    seal_target,
    verify_signature,
)
from hx_email.server.router.errors import RouteInvalidError
from hx_email.server.router.impl.outbox import claim_due, enqueue_webhook
from starlette.websockets import WebSocketDisconnect

from tests import test_router_gateway as gateway
from tests.test_router_hub import group_message

API = "/api/v1"
env = gateway.env


def user_of(settings: Any) -> int:
    with connect(settings) as connection:
        return int(connection.execute("SELECT id FROM users LIMIT 1").fetchone()[0])


def outbox_rows(settings: Any, route_id: int) -> list[dict[str, Any]]:
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT id, status, attempts, next_attempt_at FROM router_outbox "
            "WHERE kind = 'webhook' AND route_id = ? ORDER BY id",
            (route_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def test_target_sealing_signature_and_url_rules(env: dict[str, Any]) -> None:
    settings = env["settings"]
    sealed = seal_target(settings, WebhookTarget("https://hooks.example/a", "whsec_x"))
    assert "hooks.example" not in sealed
    assert open_target(settings, sealed) == WebhookTarget("https://hooks.example/a", "whsec_x")
    body = b'{"type":"ping"}'
    assert verify_signature("s", body, webhook_deliver.sign("s", body))
    assert not verify_signature("other", body, webhook_deliver.sign("s", body))
    for bad in ("ftp://x/y", "/relative", "https://user:pw@host/x"):
        with pytest.raises(RouteInvalidError):
            check_url(bad)


def test_webhook_end_to_end_signed_and_acked(
    env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, headers, qq, settings = env["client"], env["headers"], env["qq"], env["settings"]
    received: list[tuple[bytes, dict[str, str]]] = []
    arrived = threading.Event()

    def receiver(url: str, body: bytes, sent_headers: dict[str, str]) -> int:
        assert url == "https://hooks.example/in"
        received.append((body, sent_headers))
        arrived.set()
        return 204

    monkeypatch.setattr(webhook_deliver, "http_post", receiver)
    created = client.post(
        f"{API}/router/subscriptions",
        json={
            "source": f"qq:{qq}/group",
            "delivery": "webhook",
            "webhook_url": "https://hooks.example/in",
            "filter": {"contains": "deploy"},
        },
        headers=headers,
    )
    assert created.status_code == 201
    route = created.json()
    secret = route["webhook_secret"]
    assert route["webhook"]["url"] == "https://hooks.example/in"
    detail = client.get(f"{API}/router/subscriptions/{route['id']}", headers=headers).json()
    assert "webhook_secret" not in detail
    FEEDER.start(settings)
    try:
        store_envelopes(
            settings, qq, [group_message(qq, 1, "noise"), group_message(qq, 2, "deploy done")]
        )
        assert arrived.wait(5)
        deadline = time.monotonic() + 5
        while outbox_rows(settings, route["id"])[0]["status"] != "sent":
            assert time.monotonic() < deadline
            time.sleep(0.05)
        body, sent_headers = received[0]
        assert verify_signature(secret, body, sent_headers["X-HX-Router-Signature"])
        payload = json.loads(body)
        assert [m["text"] for m in payload["messages"]] == ["deploy done"]
        assert sent_headers["X-HX-Router-Delivery"].startswith("d_")
        after = client.get(f"{API}/router/subscriptions/{route['id']}", headers=headers).json()
        assert after["ack_cursor"] == payload["next_cursor"]
        log = client.get(
            f"{API}/router/subscriptions/{route['id']}/deliveries", headers=headers
        ).json()
        assert log["deliveries"][0]["status"] == "sent" and log["deliveries"][0]["messages"] == 1
        pinged = client.post(
            f"{API}/router/subscriptions/{route['id']}/webhook/ping", headers=headers
        ).json()
        assert pinged["ok"] is True and pinged["status_code"] == 204
        rotated = client.post(
            f"{API}/router/subscriptions/{route['id']}/webhook/rotate", headers=headers
        ).json()
        assert rotated["webhook_secret"] != secret
    finally:
        client.delete(f"{API}/router/subscriptions/{route['id']}", headers=headers)
        FEEDER.reload(settings)
    assert FEEDER.watching() == 0 and BUS.waiting() == 0


def test_webhook_retry_ladder_dead_hold_and_redeliver(
    env: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # 本用例手动驱动 deliver, 不让后台投递线程抢同一行
    monkeypatch.setattr(DISPATCHER, "wake", lambda _settings: None)
    client, headers, qq, settings = env["client"], env["headers"], env["qq"], env["settings"]
    route = client.post(
        f"{API}/router/subscriptions",
        json={
            "source": f"qq:{qq}/group",
            "delivery": "webhook",
            "webhook_url": "https://hooks.example/down",
        },
        headers=headers,
    ).json()
    user_id = user_of(settings)
    now = datetime.now(UTC)
    enqueue_webhook(settings, user_id, route["id"], {"messages": [], "next_cursor": ""}, 1, 1)
    entry = next(item for item in claim_due(settings, limit=50) if item.route_id == route["id"])
    status = webhook_deliver.deliver(
        settings, entry, post=lambda _u, _b, _h: 503, now=now, rng=random.Random(1)
    )
    assert status == "queued"
    due = datetime.strptime(
        outbox_rows(settings, route["id"])[0]["next_attempt_at"], "%Y-%m-%d %H:%M:%S"
    )
    assert 7 <= (due.replace(tzinfo=UTC) - now).total_seconds() <= 13
    late = now + timedelta(hours=25)
    assert webhook_deliver.deliver(settings, entry, post=lambda _u, _b, _h: 500, now=late) == "dead"
    redone = client.post(
        f"{API}/router/subscriptions/{route['id']}/deliveries/{entry.delivery_id}/redeliver",
        headers=headers,
    )
    assert redone.status_code == 200 and redone.json()["status"] == "queued"
    again = client.post(
        f"{API}/router/subscriptions/{route['id']}/deliveries/{entry.delivery_id}/redeliver",
        headers=headers,
    )
    assert again.status_code == 422
    client.patch(
        f"{API}/router/subscriptions/{route['id']}", json={"status": "paused"}, headers=headers
    )
    assert webhook_deliver.deliver(settings, entry, post=lambda _u, _b, _h: 200) == "held"
    client.patch(
        f"{API}/router/subscriptions/{route['id']}", json={"status": "active"}, headers=headers
    )
    assert outbox_rows(settings, route["id"])[0]["status"] == "queued"
    missing_url = client.post(
        f"{API}/router/subscriptions",
        json={"source": f"qq:{qq}/group", "delivery": "webhook"},
        headers=headers,
    )
    assert missing_url.status_code == 422
    client.delete(f"{API}/router/subscriptions/{route['id']}", headers=headers)
    assert outbox_rows(settings, route["id"]) == []
    FEEDER.reload(settings)


def test_websocket_feed_ack_and_auth(env: dict[str, Any]) -> None:
    client: TestClient = env["client"]
    headers, qq, settings = env["headers"], env["qq"], env["settings"]
    route = client.post(
        f"{API}/router/subscriptions", json={"source": f"qq:{qq}/group"}, headers=headers
    ).json()
    token = headers["Authorization"].removeprefix("Bearer ")
    url = f"{API}/router/subscriptions/{route['id']}/ws"

    def later() -> None:
        time.sleep(0.3)
        store_envelopes(settings, qq, [group_message(qq, 7, "over ws")])

    with client.websocket_connect(url, subprotocols=["hx-router", f"bearer.{token}"]) as socket:
        assert socket.accepted_subprotocol == "hx-router"
        ready = socket.receive_json()
        assert ready["type"] == "ready" and ready["ack_cursor"] == route["ack_cursor"]
        threading.Thread(target=later, daemon=True).start()
        frame = socket.receive_json()
        assert frame["type"] == "messages"
        assert [m["text"] for m in frame["messages"]] == ["over ws"]
        socket.send_json({"type": "ping"})
        assert socket.receive_json() == {"type": "pong"}
        socket.send_json({"type": "ack", "cursor": frame["next_cursor"]})
        assert socket.receive_json() == {"type": "acked", "ack_cursor": frame["next_cursor"]}
    stored = client.get(f"{API}/router/subscriptions/{route['id']}", headers=headers).json()
    assert stored["ack_cursor"] == frame["next_cursor"]
    with (
        pytest.raises(WebSocketDisconnect) as refused,
        client.websocket_connect(url, subprotocols=["hx-router", "bearer.nope"]),
    ):
        pass
    assert refused.value.code == 4401
    deadline = time.monotonic() + 3
    while BUS.waiting() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert BUS.waiting() == 0
