"""QQ 频道 (官方机器人): 回调验签与地址验证, 事件映射与触发信号, 发消息与错误分类, 端到端入库."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hx_email.api.impl.router.ingress.ingress_qqbot import build_qqbot_ingress_router
from hx_email.config import Settings
from hx_email.database import migrate
from hx_email.server.contract.address import parse_address, to_legacy
from hx_email.server.contract.builtin import REGISTRY
from hx_email.server.gateway.providers import HUB, InstanceRow, profile_for
from hx_email.server.gateway.sending import check_sendable
from hx_email.server.messaging.registry import creation_error
from hx_email.server.messaging.store import create_instance
from hx_email.server.router.envelope import parse_session, validate_inbound
from hx_email.server.router.impl.reader import read_messages
from hx_email.server.router.provider import OutboundPayload, SessionRef
from hx_email.server.router.providers.impl.qqbot.qqbot_contract import (
    QQBOT_PROFILE,
    classify,
    private_key,
    sign_hex,
    verify_signature,
)
from hx_email.server.router.providers.impl.qqbot.qqbot_events import payload_envelopes
from hx_email.server.router.providers.impl.qqbot.qqbot_http import BotConfig
from hx_email.server.router.providers.qqbot import QQBotProvider

SECRET = "naOC0ocQE3shWLAfffVLB1rhYPG7"
CONFIG = BotConfig("102000001", SECRET)


def event(t: str = "AT_MESSAGE_CREATE", **data: object) -> dict[str, object]:
    message: dict[str, object] = {
        "id": "08f1a2b3",
        "guild_id": "18700000000001",
        "channel_id": "100010",
        "content": "<@!99> 帮我查一下",
        "timestamp": "2026-11-09T00:10:00+08:00",
        "author": {"id": "1234", "username": "abc", "bot": False},
        "mentions": [{"id": "99", "username": "hx-bot", "bot": True}],
        "seq": 101,
    }
    message.update(data)
    return {"id": "AT_MESSAGE_CREATE:1", "op": 0, "s": 1, "t": t, "d": message}


def signed(body: bytes, timestamp: str = "1636373772") -> dict[str, str]:
    return {
        "X-Signature-Timestamp": timestamp,
        "X-Signature-Ed25519": sign_hex(SECRET, timestamp.encode() + body),
    }


def test_signature_seed_and_verify() -> None:
    body = b'{"msg":"hello"}'
    headers = signed(body)
    assert verify_signature(
        SECRET, headers["X-Signature-Timestamp"], body, headers["X-Signature-Ed25519"]
    )
    assert not verify_signature(SECRET, "1", body, headers["X-Signature-Ed25519"])
    assert not verify_signature(SECRET, "1", body, "zz")
    assert not verify_signature("other", "1636373772", body, headers["X-Signature-Ed25519"])
    short = private_key("abc").private_bytes_raw()
    assert short == (b"abc" * 16)[:32]


def test_capabilities_address_and_profile() -> None:
    caps = REGISTRY.get("qqbot")
    assert caps is not None and caps.risk_level == "official" and caps.rate_profile == "qqbot"
    address = parse_address("qqbot:5/guild/18700000000001/channel/100010")
    assert to_legacy(address) == "qqbot:5:channel:18700000000001/100010"
    assert parse_session("qqbot:5:channel:18700000000001/100010").session_type == "channel"
    instance = InstanceRow(5, 1, "qqbot", "bot", "online", {})
    assert profile_for(instance, "channel") is QQBOT_PROFILE
    check_sendable(instance, parse_session("qqbot:5:channel:1/2"), "")


def test_events_map_mentions_and_replies() -> None:
    [env] = payload_envelopes(5, event())
    validate_inbound(env, 5)
    assert env["session"] == "qqbot:5:channel:18700000000001/100010"
    assert env["text"] == "@hx-bot 帮我查一下" and env["occurred_at"] == "2026-11-08T16:10:00Z"
    assert env["flags"] == {"from_self": False, "mention_self": True, "reply_to_self": False}
    reply = event(content="好的", mentions=[], message_reference={"message_id": "07aa"})
    [env] = payload_envelopes(5, reply)
    assert env["reply_to"] == "07aa" and env["flags"]["reply_to_self"] is True  # type: ignore[index]
    [env] = payload_envelopes(5, event("MESSAGE_CREATE", content="随便聊", mentions=[]))
    assert env["flags"]["reply_to_self"] is False  # type: ignore[index]
    assert payload_envelopes(5, event("GUILD_CREATE")) == []
    assert payload_envelopes(5, event(guild_id="x")) == []
    assert payload_envelopes(5, {"op": 13, "d": {}}) == []


class FakeResponse:
    def __init__(self, status_code: int, body: object) -> None:
        self.status_code = status_code
        self.body = body

    def json(self) -> object:
        return self.body


class FakeHttp:
    def __init__(self, *replies: object) -> None:
        self.replies: list[object] = list(replies)
        self.calls: list[dict[str, object]] = []

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append({"url": url} | kwargs)
        reply: object = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        assert isinstance(reply, FakeResponse)
        return reply


def token() -> FakeResponse:
    return FakeResponse(200, {"access_token": "T", "expires_in": "7200"})


def channel_ref(peer: str = "18700000000001/100010") -> SessionRef:
    return SessionRef(f"qqbot:5:channel:{peer}", "qqbot", 5, "channel", peer, "")


def test_send_passive_active_and_errors() -> None:
    http = FakeHttp(token(), FakeResponse(200, {"id": "m1"}), FakeResponse(200, {"id": "m2"}))
    provider = QQBotProvider(5, CONFIG, http)
    sent = provider.send(channel_ref(), OutboundPayload("d_1", "收到", "08f1a2b3", ""))
    assert (sent.status, sent.platform_message_id) == ("sent", "m1")
    call = http.calls[1]
    assert call["url"] == "https://api.bot.qq.com/channels/100010/messages"
    assert call["json"] == {"content": "收到", "msg_id": "08f1a2b3"}
    assert call["headers"] == {"Authorization": "QQBot T", "X-Union-Appid": "102000001"}
    active = provider.send(channel_ref(), OutboundPayload("d_2", "早", "", ""))
    assert active.status == "sent" and http.calls[2]["json"] == {"content": "早"}
    assert len(http.calls) == 3  # token cached
    assert provider.send(channel_ref("bad"), OutboundPayload("d", "x", "", "")).status == "failed"
    limited = classify(200, 304045, "子频道主动消息数限频")
    assert limited.status == "retry" and limited.risk_signal
    assert classify(200, 304027, "").error_code == "reply_window_expired"
    assert classify(200, 304023, "", "a-1").platform_message_id == "audit:a-1"
    assert (
        classify(200, 11265, "").risk_signal and classify(401, 0, "").error_code == "provider_auth"
    )
    assert classify(502, 0, "").status == "retry"
    timeout = QQBotProvider(5, CONFIG, FakeHttp(token(), requests.Timeout("slow")))
    assert timeout.send(channel_ref(), OutboundPayload("d", "x", "", "")).status == "unknown"
    denied = QQBotProvider(5, CONFIG, FakeHttp(FakeResponse(200, {"code": 100016})))
    assert (
        denied.send(channel_ref(), OutboundPayload("d", "x", "", "")).error_code == "provider_auth"
    )


@pytest.fixture()
def bot(tmp_path: Path) -> Iterator[tuple[TestClient, Settings, int]]:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    instance = create_instance(
        settings, 1, "qqbot", "bot", {"app_id": CONFIG.app_id, "app_secret": SECRET}
    )
    app = FastAPI()
    app.include_router(build_qqbot_ingress_router(settings))
    HUB.forget(instance.id)
    yield TestClient(app), settings, instance.id
    HUB.forget(instance.id)


def test_ingress_validates_verifies_and_stores(bot: tuple[TestClient, Settings, int]) -> None:
    client, settings, instance_id = bot
    url = f"/api/v1/router/ingress/qqbot/{instance_id}"
    check = {"op": 13, "d": {"plain_token": "Arq0D5A61EgUu4OxUvOp", "event_ts": "1725442341"}}
    reply = client.post(url, content=json.dumps(check)).json()
    expected = sign_hex(SECRET, b"1725442341Arq0D5A61EgUu4OxUvOp")
    assert reply == {"plain_token": "Arq0D5A61EgUu4OxUvOp", "signature": expected}
    body = json.dumps(event()).encode()
    assert client.post(url, content=body, headers={"X-Signature-Ed25519": "00"}).status_code == 401
    assert client.post(url, content=body, headers=signed(body)).json() == {"op": 12, "d": 0}
    assert client.post(url, content=body, headers=signed(body)).status_code == 200
    page = read_messages(settings, 1, f"qqbot:{instance_id}/guild/18700000000001", "", limit=10)
    assert [message.text for message in page.messages] == ["@hx-bot 帮我查一下"]
    assert client.post("/api/v1/router/ingress/qqbot/999", content=body).status_code == 404


def test_qqbot_instance_needs_app_credentials() -> None:
    assert creation_error("qqbot", {"app_id": "1", "app_secret": "s"}) is None
    assert creation_error("qqbot", {"app_id": "1"}) is not None
    assert creation_error("wechat", {}) is not None
