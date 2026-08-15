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


def test_connect_with_unreachable_onebot_reports_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login(client, settings)
    instance = create_qq_instance(client, headers)

    import requests

    def fake_post(
        self: Any,
        url: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 10.0,
    ) -> FakeOneBotResponse:
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr("hx_email.server.messaging.onebot.requests.Session.post", fake_post)

    response = client.post(f"{API}/messaging/instances/{instance['id']}/connect", headers=headers)
    assert response.status_code == 400
    assert "OneBot 请求失败" in response.json()["detail"]


def test_create_qq_instance_with_empty_config_gets_defaults(tmp_path: Any) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login(client, settings)

    response = client.post(
        f"{API}/messaging/instances",
        json={"kind": "qq", "name": "zero-config"},
        headers=headers,
    )
    assert response.status_code == 201
    instance = response.json()["instance"]
    assert instance["config"]["api_base_url"] == "http://127.0.0.1:3000"
    assert instance["config"]["webui_url"] == "http://127.0.0.1:6099/webui"
    assert instance["config"]["event_token"] == "***"


class FakeGetResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code: int = status_code


def test_login_probe_reports_unreachable_napcat(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login(client, settings)
    instance = create_qq_instance(client, headers)

    import requests

    def fake_get(url: str, timeout: float = 10.0) -> FakeGetResponse:
        raise requests.ConnectionError("refused")

    monkeypatch.setattr("hx_email.server.messaging.impl.probe.requests.get", fake_get)

    response = client.post(
        f"{API}/messaging/instances/{instance['id']}/login/probe", headers=headers
    )
    assert response.status_code == 200
    probe = response.json()["probe"]
    assert probe["webui_reachable"] is False
    assert probe["api_reachable"] is False
    assert "NapCat 未启动" in probe["message"]


def test_login_probe_reports_online_when_endpoints_respond(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login(client, settings)
    instance = create_qq_instance(client, headers)

    def fake_get(url: str, timeout: float = 10.0) -> FakeGetResponse:
        return FakeGetResponse(200)

    monkeypatch.setattr("hx_email.server.messaging.impl.probe.requests.get", fake_get)

    response = client.post(
        f"{API}/messaging/instances/{instance['id']}/login/probe", headers=headers
    )
    assert response.status_code == 200
    probe = response.json()["probe"]
    assert probe["webui_reachable"] is True
    assert probe["api_reachable"] is True
    assert "NapCat 在线" in probe["message"]


def test_update_instance_config_merges_and_masks_token(tmp_path: Any) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login(client, settings)
    instance = create_qq_instance(client, headers)

    response = client.put(
        f"{API}/messaging/instances/{instance['id']}/config",
        json={"config": {"webui_url": "http://10.0.0.2:6099/webui"}},
        headers=headers,
    )
    assert response.status_code == 200
    updated = response.json()["instance"]
    assert updated["config"]["webui_url"] == "http://10.0.0.2:6099/webui"
    assert updated["config"]["api_base_url"] == "http://127.0.0.1:3000"
    assert updated["config"]["event_token"] == "***"


class FakeEngineProcess:
    def __init__(self, pid: int) -> None:
        self.pid: int = pid

    def poll(self) -> None:
        return None


def test_generate_lagrange_config_shape() -> None:
    from hx_email.server.messaging.engine import generate_lagrange_config

    config = generate_lagrange_config(
        api_port=31001, webui_port=31002, event_url="http://x/ev", access_token="tok"
    )
    implementations = config["OneBot11"]["Implementations"]
    assert implementations[0]["Type"] == "Http"
    assert implementations[0]["Port"] == 31001
    assert implementations[1]["Type"] == "HttpPost"
    assert implementations[1]["PostUrls"] == ["http://x/ev"]
    assert config["WebUi"]["Port"] == 31002


def test_engine_manager_start_qr_and_stop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    from hx_email.server.messaging.engine import QQEngineManager

    settings = make_settings(tmp_path)
    manager = QQEngineManager(settings, instance_id=7)
    executable = manager._dir / "Lagrange.OneBot"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)

    monkeypatch.setattr(
        "hx_email.server.messaging.engine.subprocess.Popen",
        lambda *args, **kwargs: FakeEngineProcess(424242),
    )
    monkeypatch.setattr(QQEngineManager, "_api_ready", lambda self, port: True)
    monkeypatch.setattr(QQEngineManager, "_alive", staticmethod(lambda pid: True))

    pid = manager.start(
        api_port=31001,
        webui_port=31002,
        event_url="http://127.0.0.1:8000/ev",
        access_token="tok",
    )
    assert pid == 424242
    assert (manager._dir / "engine.pid").read_text().strip() == "424242"
    assert "OneBot11" in (manager._dir / "appsettings.json").read_text()

    def fake_get(url: str, timeout: float = 10.0) -> FakeGetResponse:
        assert "31002" in url
        response = FakeGetResponse(200)
        response.content = b"PNGDATA"
        response.headers = {"content-type": "image/png"}
        return response

    monkeypatch.setattr("hx_email.server.messaging.engine.requests.get", fake_get)
    assert manager.qr_image(31002) == b"PNGDATA"

    manager.stop()
    assert not (manager._dir / "engine.pid").exists()


def test_engine_start_stop_and_qr_routes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    from hx_email.server.messaging.engine import QQEngineManager

    settings = make_settings(tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login(client, settings)
    instance = create_qq_instance(client, headers)

    monkeypatch.setattr(QQEngineManager, "start", lambda self, *args, **kwargs: 12345)
    monkeypatch.setattr(QQEngineManager, "stop", lambda self: None)
    monkeypatch.setattr(QQEngineManager, "qr_image", lambda self, webui_port: b"PNGDATA")

    started = client.post(
        f"{API}/messaging/instances/{instance['id']}/engine/start", headers=headers
    )
    assert started.status_code == 200
    assert started.json()["pid"] == 12345
    assert started.json()["instance"]["config"]["api_base_url"].startswith("http://127.0.0.1:")

    qr = client.get(f"{API}/messaging/instances/{instance['id']}/login/qr", headers=headers)
    assert qr.status_code == 200
    assert qr.headers["content-type"] == "image/png"
    assert qr.content == b"PNGDATA"

    stopped = client.post(
        f"{API}/messaging/instances/{instance['id']}/engine/stop", headers=headers
    )
    assert stopped.status_code == 200


def test_resolve_default_download_url_uses_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hx_email.server.messaging.engine import resolve_default_download_url

    monkeypatch.setenv("HX_EMAIL_QQ_ENGINE_URL", "http://mirror/engine.zip")
    assert resolve_default_download_url() == "http://mirror/engine.zip"


def test_resolve_default_download_url_uses_pinned_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hx_email.server.messaging.engine import (
        LAGRANGE_PINNED_VERSION,
        default_asset_rid,
        resolve_default_download_url,
    )

    monkeypatch.delenv("HX_EMAIL_QQ_ENGINE_URL", raising=False)
    monkeypatch.delenv("HX_EMAIL_QQ_ENGINE_VERSION", raising=False)
    url = resolve_default_download_url()
    rid = default_asset_rid()
    assert "/releases/download/" in url
    assert url.endswith(f"Lagrange.OneBot_{LAGRANGE_PINNED_VERSION}_{rid}.zip")


def test_resolve_default_download_url_honors_version_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hx_email.server.messaging.engine import (
        default_asset_rid,
        resolve_default_download_url,
    )

    monkeypatch.delenv("HX_EMAIL_QQ_ENGINE_URL", raising=False)
    monkeypatch.setenv("HX_EMAIL_QQ_ENGINE_VERSION", "9.9.9")
    url = resolve_default_download_url()
    rid = default_asset_rid()
    assert url.endswith(f"Lagrange.OneBot_9.9.9_{rid}.zip")


def test_ensure_installed_download_failure_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    import requests
    from hx_email.server.messaging.engine import QQEngineManager

    settings = make_settings(tmp_path)
    manager = QQEngineManager(settings, instance_id=11)
    manager._dir.mkdir(parents=True)

    def fake_get(url: str, stream: bool = False, timeout: float = 10.0) -> FakeGetResponse:
        raise requests.ConnectionError("network down")

    monkeypatch.setattr("hx_email.server.messaging.engine.requests.get", fake_get)

    with pytest.raises(RuntimeError, match="下载失败"):
        manager.ensure_installed(download_url="http://127.0.0.1:1/engine.zip")


def test_engine_qr_image_falls_back_to_qr_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    import requests
    from hx_email.server.messaging.engine import QQEngineManager

    settings = make_settings(tmp_path)
    manager = QQEngineManager(settings, instance_id=9)
    manager._dir.mkdir(parents=True)
    (manager._dir / "engine.pid").write_text("4242")
    (manager._dir / "qr-0.png").write_bytes(b"PNGFILE")
    monkeypatch.setattr(QQEngineManager, "_alive", staticmethod(lambda pid: True))

    def fake_get(url: str, timeout: float = 10.0) -> FakeGetResponse:
        raise requests.ConnectionError("engine webui not serving http")

    monkeypatch.setattr("hx_email.server.messaging.engine.requests.get", fake_get)
    assert manager.qr_image(22000) == b"PNGFILE"
