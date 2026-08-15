"""Tests for the messaging plugin framework and the QQ OneBot adapter."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate
from hx_email.server.messaging.registry import clear_runtime

API = "/api/v1"


class FakeOneBotResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload: dict[str, Any] = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


@pytest.fixture(autouse=True)
def reset_adapter_runtime() -> None:
    clear_runtime()
    yield
    clear_runtime()


def make_settings(tmp_path: Any) -> Settings:
    return Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")


def login(client: TestClient, settings: Settings) -> dict[str, str]:
    session = client.post(
        f"{API}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    ).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def create_qq_instance(
    client: TestClient,
    headers: dict[str, str],
    event_token: str = "secret-token",
    api_base_url: str = "http://127.0.0.1:3000",
) -> dict[str, Any]:
    response = client.post(
        f"{API}/messaging/instances",
        json={
            "kind": "qq",
            "name": "my-qq",
            "config": {
                "api_base_url": api_base_url,
                "webui_url": "http://127.0.0.1:6099/webui",
                "event_token": event_token,
            },
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["instance"]


def test_messaging_catalog_lists_four_platforms(tmp_path: Any) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login(client, settings)

    response = client.get(f"{API}/messaging/catalog", headers=headers)

    assert response.status_code == 200
    plugins = response.json()["plugins"]
    assert [item["key"] for item in plugins] == ["qq", "wechat", "telegram", "discord"]
    qq = next(item for item in plugins if item["key"] == "qq")
    assert qq["available"] is True
    assert qq["capabilities"]["supports_qr_login"] is True
    assert qq["capabilities"]["supports_groups"] is True


def test_messaging_catalog_requires_auth(tmp_path: Any) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))

    response = client.get(f"{API}/messaging/catalog")

    assert response.status_code == 401


def test_create_and_list_qq_instance(tmp_path: Any) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login(client, settings)

    instance = create_qq_instance(client, headers)
    assert instance["kind"] == "qq"
    assert instance["status"] == "stopped"
    assert instance["config"]["api_base_url"] == "http://127.0.0.1:3000"

    listed = client.get(f"{API}/messaging/instances", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["instances"]) == 1
    assert listed.json()["instances"][0]["capabilities"]["risk_level"] == "third_party"


def test_instance_is_user_scoped(tmp_path: Any) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login(client, settings)
    instance = create_qq_instance(client, headers)

    client.put(f"{API}/admin/settings/registration", json={"enabled": True}, headers=headers)
    other = client.post(
        f"{API}/auth/register",
        json={"username": "alice", "password": "alice-pass"},
    ).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}

    response = client.get(f"{API}/messaging/instances/{instance['id']}", headers=other_headers)
    assert response.status_code == 404
    delete_response = client.delete(
        f"{API}/messaging/instances/{instance['id']}", headers=other_headers
    )
    assert delete_response.status_code == 404


def test_event_ingest_requires_valid_token(tmp_path: Any) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login(client, settings)
    create_qq_instance(client, headers, event_token="right-token")

    bad = client.post(
        f"{API}/messaging/events/qq",
        json={"post_type": "message", "message_type": "group", "group_id": 1},
        headers={"X-Messaging-Token": "wrong-token"},
    )
    assert bad.status_code == 401

    no_token = client.post(
        f"{API}/messaging/events/qq",
        json={"post_type": "message", "message_type": "group", "group_id": 1},
    )
    assert no_token.status_code == 401


def test_event_ingest_stores_inbound_message(tmp_path: Any) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login(client, settings)
    instance = create_qq_instance(client, headers, event_token="right-token")

    response = client.post(
        f"{API}/messaging/events/qq",
        json={
            "post_type": "message",
            "message_type": "group",
            "group_id": 10001,
            "user_id": 20001,
            "sender": {"nickname": "alice"},
            "raw_message": "hello from qq",
            "message_id": "evt-1",
        },
        headers={"X-Messaging-Token": "right-token"},
    )
    assert response.status_code == 200
    assert response.json()["stored"] is True

    messages = client.get(
        f"{API}/messaging/instances/{instance['id']}/messages",
        params={"chat_id": "10001"},
        headers=headers,
    ).json()["messages"]
    assert len(messages) == 1
    assert messages[0]["direction"] == "inbound"
    assert messages[0]["text"] == "hello from qq"
    assert messages[0]["chat_type"] == "group"


def test_send_message_via_onebot(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login(client, settings)
    instance = create_qq_instance(client, headers)

    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_post(
        self: Any,
        url: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 10.0,
    ) -> FakeOneBotResponse:
        calls.append((url, json or {}))
        return FakeOneBotResponse({"status": "ok", "retcode": 0, "data": {"message_id": 42}})

    monkeypatch.setattr("hx_email.server.messaging.onebot.requests.Session.post", fake_post)

    response = client.post(
        f"{API}/messaging/instances/{instance['id']}/send",
        json={"chat_id": "30001", "chat_type": "group", "text": "hi"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["message_id"] == "42"
    assert calls[0][0].endswith("/send_group_msg")
    assert calls[0][1]["group_id"] == 30001
    assert calls[0][1]["message"] == "hi"


def test_login_ticket_and_status(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login(client, settings)
    instance = create_qq_instance(client, headers)

    login_response = client.post(
        f"{API}/messaging/instances/{instance['id']}/login", headers=headers
    )
    assert login_response.status_code == 200
    assert login_response.json()["login"]["mode"] == "redirect"
    assert "6099/webui" in login_response.json()["login"]["url"]

    def fake_post(
        self: Any,
        url: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 10.0,
    ) -> FakeOneBotResponse:
        return FakeOneBotResponse(
            {"status": "ok", "retcode": 0, "data": {"user_id": 123456, "nickname": "bot"}}
        )

    monkeypatch.setattr("hx_email.server.messaging.onebot.requests.Session.post", fake_post)

    status_response = client.post(
        f"{API}/messaging/instances/{instance['id']}/login/status", headers=headers
    )
    assert status_response.status_code == 200
    assert status_response.json()["login"]["logged_in"] is True
    assert status_response.json()["login"]["account_id"] == "123456"


def test_group_list_and_action(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login(client, settings)
    instance = create_qq_instance(client, headers)

    def fake_post(
        self: Any,
        url: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 10.0,
    ) -> FakeOneBotResponse:
        if url.endswith("/get_group_list"):
            return FakeOneBotResponse(
                {
                    "status": "ok",
                    "retcode": 0,
                    "data": {"data": [{"group_id": 777, "group_name": "dev", "member_count": 12}]},
                }
            )
        return FakeOneBotResponse({"status": "ok", "retcode": 0, "data": {}})

    monkeypatch.setattr("hx_email.server.messaging.onebot.requests.Session.post", fake_post)

    groups = client.get(f"{API}/messaging/instances/{instance['id']}/groups", headers=headers)
    assert groups.status_code == 200
    assert groups.json()["groups"][0]["name"] == "dev"

    kick = client.post(
        f"{API}/messaging/instances/{instance['id']}/groups/777/action",
        json={"action": "kick", "member_id": "555"},
        headers=headers,
    )
    assert kick.status_code == 200
    assert kick.json()["applied"] is True


def test_connect_without_api_base_url_reports_error(tmp_path: Any) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login(client, settings)
    instance = create_qq_instance(client, headers, api_base_url="")

    response = client.post(f"{API}/messaging/instances/{instance['id']}/connect", headers=headers)
    assert response.status_code == 400
    assert "api_base_url" in response.json()["detail"]
