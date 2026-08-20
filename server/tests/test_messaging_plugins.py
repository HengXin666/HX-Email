"""Tests for the messaging plugin framework and the QQ OneBot adapter."""

from __future__ import annotations

import asyncio
import types
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


class FakeLagrangeClient:
    def __init__(self) -> None:
        self.online: asyncio.Event = asyncio.Event()
        self.uin: int = 123456
        self.sent: list[tuple[object, ...]] = []

    async def stop(self) -> None:
        return None

    async def send_grp_msg(self, msg_chain: list[object], grp_id: int) -> int:
        self.sent.append(("group", grp_id))
        return 42

    async def send_friend_msg(self, msg_chain: list[object], uid: str) -> int:
        self.sent.append(("friend", uid))
        return 43

    async def get_friend_list(self) -> list[object]:
        return [types.SimpleNamespace(uin=30001, uid="u_30001", nickname="alice", remark="Alice")]

    async def get_grp_list(self) -> object:
        return types.SimpleNamespace(
            groups=[types.SimpleNamespace(group_id=777, group_name="dev", member_count=12)]
        )

    async def get_grp_msg(self, grp_id: int, start: int, end: int = 0) -> list[object]:
        return [
            types.SimpleNamespace(
                grp_id=grp_id, uin=200, nickname="bob", msg="hi", seq=5, time=1700000000
            )
        ]

    async def kick_grp_member(self, grp_id: int, uin: int, permanent: bool = False) -> None:
        self.sent.append(("kick", grp_id, uin))

    async def set_mute_member(self, grp_id: int, uin: int, duration: int) -> None:
        self.sent.append(("mute", grp_id, uin, duration))

    async def set_mute_grp(self, grp_id: int, enable: bool) -> None:
        self.sent.append(("mute_all", grp_id, enable))

    async def leave_grp(self, grp_id: int) -> None:
        self.sent.append(("leave", grp_id))


class FakeLagrangeEngine:
    def __init__(self, client: FakeLagrangeClient) -> None:
        self._client: FakeLagrangeClient = client
        self._error: str = ""

    def is_running(self) -> bool:
        return True


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


def test_send_message_via_onebot_http(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
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


def test_login_ticket_and_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login(client, settings)
    instance = create_qq_instance(client, headers)

    login_response = client.post(
        f"{API}/messaging/instances/{instance['id']}/login", headers=headers
    )
    assert login_response.status_code == 200
    assert login_response.json()["login"]["mode"] == "qr"
    assert "/login/qr" in login_response.json()["login"]["qr_image_url"]

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


def test_group_list_and_action(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
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


def test_connect_without_engine_reports_error(
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


class FakeDiscoveryPage:
    def __init__(
        self,
        text: str = "",
        status_code: int = 200,
        json_payload: object = None,
    ) -> None:
        self.text: str = text
        self.status_code: int = status_code
        self._json_payload: object = json_payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        if self._json_payload is None:
            raise ValueError("no json payload")
        return self._json_payload


def test_login_probe_reports_unreachable_engine(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login(client, settings)
    instance = create_qq_instance(client, headers)

    monkeypatch.setattr("hx_email.server.messaging.impl.probe.get_engine", lambda instance_id: None)

    response = client.post(
        f"{API}/messaging/instances/{instance['id']}/login/probe", headers=headers
    )
    assert response.status_code == 200
    probe = response.json()["probe"]
    assert probe["api_reachable"] is False
    assert "引擎未启动" in probe["message"]


def test_login_probe_reports_engine_ready(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    settings = make_settings(tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login(client, settings)
    instance = create_qq_instance(client, headers)

    class ReadyEngine:
        def is_running(self) -> bool:
            return True

        def qr_image(self, webui_port: int = 0) -> bytes | None:
            return b"PNG"

    monkeypatch.setattr(
        "hx_email.server.messaging.impl.probe.get_engine", lambda instance_id: ReadyEngine()
    )

    response = client.post(
        f"{API}/messaging/instances/{instance['id']}/login/probe", headers=headers
    )
    assert response.status_code == 200
    probe = response.json()["probe"]
    assert probe["api_reachable"] is True
    assert "可以扫码登录" in probe["message"]


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


def test_engine_start_raises_when_container_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    from hx_email.server.messaging.engine import QQEngineManager

    settings = make_settings(tmp_path)
    manager = QQEngineManager(settings, instance_id=16)

    class R:
        def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
            self.returncode: int = returncode
            self.stdout: str = stdout
            self.stderr: str = stderr

    def fake_docker(self: QQEngineManager, *args: str) -> R:
        cmd: list[str] = list(args)
        if cmd[:2] == ["image", "inspect"]:
            return R(0)
        if cmd[0] == "run":
            return R(1, stderr="docker run failed")
        return R(0)

    monkeypatch.setattr(QQEngineManager, "_ensure_docker_ready", lambda self: None)
    monkeypatch.setattr(QQEngineManager, "_docker", fake_docker)

    with pytest.raises(RuntimeError, match="NapCat 容器启动失败"):
        manager.start()


def test_engine_pull_falls_back_to_mirror_and_tags(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """官方源 pull 失败时回退镜像源, 并 tag 回官方名后再启动容器。"""
    from hx_email.server.messaging import engine as engine_module
    from hx_email.server.messaging.engine import QR_FILE_NAME, QQEngineManager

    settings = make_settings(tmp_path)
    manager = QQEngineManager(settings, instance_id=18)

    class R:
        def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
            self.returncode: int = returncode
            self.stdout: str = stdout
            self.stderr: str = stderr

    pulled: list[list[str]] = []
    tagged: list[list[str]] = []

    def fake_pull(self: QQEngineManager, *args: str) -> R:
        pulled.append(list(args))
        image: str = args[1]
        # 官方源失败, 镜像源成功
        return R(0) if image.startswith(("docker.m.daocloud.io/", "docker.1ms.run/")) else R(1)

    def fake_docker(self: QQEngineManager, *args: str) -> R:
        cmd: list[str] = list(args)
        if cmd[:2] == ["image", "inspect"]:
            return R(1)  # 镜像不存在 → 触发拉取
        if cmd[0] == "tag":
            tagged.append(list(args))
            return R(0)
        if cmd[0] == "run":
            (manager._dir / "cache").mkdir(parents=True, exist_ok=True)
            (manager._dir / "cache" / QR_FILE_NAME).write_bytes(b"QR")
            return R(0)
        if cmd[:2] == ["inspect", "-f"]:
            return R(0, stdout="true")
        return R(0)

    monkeypatch.setattr(engine_module, "DOCKER_MIRRORS", ("docker.m.daocloud.io", "docker.1ms.run"))
    monkeypatch.setattr(QQEngineManager, "_ensure_docker_ready", lambda self: None)
    monkeypatch.setattr(QQEngineManager, "_docker_pull", fake_pull)
    monkeypatch.setattr(QQEngineManager, "_docker", fake_docker)

    pid: int = manager.start(api_port=31011, webui_port=31012, access_token="tok")

    assert pid == 10018
    pull_images: list[str] = [args[1] for args in pulled]
    assert pull_images[0] == engine_module.NAPCAT_IMAGE
    assert pull_images[1] == "docker.m.daocloud.io/" + engine_module.NAPCAT_IMAGE
    assert tagged[0][1] == pull_images[1]
    assert tagged[0][2] == engine_module.NAPCAT_IMAGE
    assert manager.qr_image() == b"QR"


def test_engine_pull_raises_clear_error_when_all_sources_fail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    from hx_email.server.messaging.engine import QQEngineManager

    settings = make_settings(tmp_path)
    manager = QQEngineManager(settings, instance_id=19)

    class R:
        def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
            self.returncode: int = returncode
            self.stdout: str = stdout
            self.stderr: str = stderr

    def fake_pull(self: QQEngineManager, *args: str) -> R:
        return R(1, stderr="dial tcp: lookup registry-1.docker.io: i/o timeout")

    def fake_docker(self: QQEngineManager, *args: str) -> R:
        cmd: list[str] = list(args)
        if cmd[:2] == ["image", "inspect"]:
            return R(1)  # 镜像不存在 → 触发拉取
        return R(0)

    monkeypatch.setattr(QQEngineManager, "_ensure_docker_ready", lambda self: None)
    monkeypatch.setattr(QQEngineManager, "_docker_pull", fake_pull)
    monkeypatch.setattr(QQEngineManager, "_docker", fake_docker)

    with pytest.raises(RuntimeError, match="NapCat 镜像下载失败"):
        manager.start()


def test_engine_preflight_reports_missing_docker_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    from hx_email.server.messaging.engine import QQEngineManager

    settings = make_settings(tmp_path)
    manager = QQEngineManager(settings, instance_id=20)
    monkeypatch.setattr("hx_email.server.messaging.engine.shutil.which", lambda _: None)

    with pytest.raises(RuntimeError, match="未检测到 docker CLI"):
        manager.start()


def test_engine_preflight_reports_unreachable_daemon(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:

    from hx_email.server.messaging.engine import QQEngineManager

    settings = make_settings(tmp_path)
    manager = QQEngineManager(settings, instance_id=21)

    class R:
        def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
            self.returncode: int = returncode
            self.stdout: str = stdout
            self.stderr: str = stderr

    monkeypatch.setattr(
        "hx_email.server.messaging.engine.shutil.which", lambda _: "/usr/local/bin/docker"
    )
    monkeypatch.setattr(
        "hx_email.server.messaging.engine.subprocess.run",
        lambda *args, **kwargs: R(1, stderr="Cannot connect to the Docker daemon"),
    )

    with pytest.raises(RuntimeError, match="无法连接宿主机 Docker"):
        manager.start()


def test_engine_preflight_reports_daemon_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    import subprocess

    from hx_email.server.messaging.engine import QQEngineManager

    settings = make_settings(tmp_path)
    manager = QQEngineManager(settings, instance_id=22)
    monkeypatch.setattr(
        "hx_email.server.messaging.engine.shutil.which", lambda _: "/usr/local/bin/docker"
    )

    def raise_timeout(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=["docker", "info"], timeout=30)

    monkeypatch.setattr(
        "hx_email.server.messaging.engine.subprocess.run",
        raise_timeout,
    )

    with pytest.raises(RuntimeError, match="docker info 超时"):
        manager.start()


def test_engine_manager_start_qr_and_stop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    from hx_email.server.messaging.engine import QR_FILE_NAME, QQEngineManager, get_engine

    settings = make_settings(tmp_path)
    manager = QQEngineManager(settings, instance_id=7)
    state: dict[str, bool] = {"running": False}

    class R:
        def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
            self.returncode: int = returncode
            self.stdout: str = stdout
            self.stderr: str = stderr

    def fake_docker(self: QQEngineManager, *args: str) -> R:
        cmd: list[str] = list(args)
        if cmd[:2] == ["image", "inspect"]:
            return R(0)
        if cmd[:2] == ["rm", "-f"]:
            state["running"] = False
            return R(0)
        if cmd[0] == "run":
            (manager._dir / "cache").mkdir(parents=True, exist_ok=True)
            (manager._dir / "cache" / QR_FILE_NAME).write_bytes(b"QRDATA")
            state["running"] = True
            return R(0)
        if cmd[:2] == ["inspect", "-f"]:
            return R(0, stdout="true" if state["running"] else "false")
        return R(0)

    monkeypatch.setattr(QQEngineManager, "_ensure_docker_ready", lambda self: None)
    monkeypatch.setattr(QQEngineManager, "_docker", fake_docker)

    pid = manager.start(
        api_port=31001,
        webui_port=31002,
        event_url="http://127.0.0.1:8000/ev",
        access_token="tok",
    )
    assert pid == 10007
    assert manager.is_running() is True
    assert manager.qr_image() == b"QRDATA"
    assert get_engine(7) is manager
    assert (manager._dir / "config" / "onebot11.json").exists()
    assert (manager._dir / "config" / "webui.json").exists()

    manager.stop()
    assert manager.is_running() is False
    assert get_engine(7) is None


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


def test_resolve_default_download_url_discovers_latest_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hx_email.server.messaging.impl.discovery import (
        default_asset_rid,
        resolve_default_download_url,
    )

    monkeypatch.delenv("HX_EMAIL_QQ_ENGINE_URL", raising=False)
    monkeypatch.delenv("HX_EMAIL_QQ_ENGINE_VERSION", raising=False)
    rid = default_asset_rid()
    expected = (
        "https://github.com/LagrangeDev/Lagrange.Core/releases/download/0.25.0/"
        f"Lagrange.OneBot_0.25.0_{rid}.zip"
    )

    calls: list[str] = []

    def fake_get(url: str, **kwargs: object) -> FakeDiscoveryPage:
        calls.append(url)
        if "api.github.com" in url:
            return FakeDiscoveryPage(status_code=403)
        return FakeDiscoveryPage(text=f'"tag_name":"0.25.0" "browser_download_url":"{expected}"')

    monkeypatch.setattr("hx_email.server.messaging.impl.discovery.requests.get", fake_get)

    assert resolve_default_download_url() == expected
    assert len(calls) == 2


def test_resolve_default_download_url_falls_back_to_expanded_assets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hx_email.server.messaging.impl.discovery import (
        default_asset_rid,
        resolve_default_download_url,
    )

    monkeypatch.delenv("HX_EMAIL_QQ_ENGINE_URL", raising=False)
    monkeypatch.delenv("HX_EMAIL_QQ_ENGINE_VERSION", raising=False)
    rid = default_asset_rid()
    expected = (
        "https://github.com/LagrangeDev/Lagrange.Core/releases/download/0.25.0/"
        f"Lagrange.OneBot_0.25.0_{rid}.zip"
    )
    asset_href = (
        f"/LagrangeDev/Lagrange.Core/releases/download/0.25.0/Lagrange.OneBot_0.25.0_{rid}.zip"
    )

    def fake_get(url: str, **kwargs: object) -> FakeDiscoveryPage:
        if "api.github.com" in url:
            return FakeDiscoveryPage(status_code=403)
        if "expanded_assets" in url:
            return FakeDiscoveryPage(text=f'<a href="{asset_href}">x</a>')
        return FakeDiscoveryPage(text='"tag_name":"0.25.0"')

    monkeypatch.setattr("hx_email.server.messaging.impl.discovery.requests.get", fake_get)

    assert resolve_default_download_url() == expected


def test_resolve_default_download_url_falls_back_to_atom_feed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hx_email.server.messaging.impl.discovery import (
        default_asset_rid,
        resolve_default_download_url,
    )

    monkeypatch.delenv("HX_EMAIL_QQ_ENGINE_URL", raising=False)
    monkeypatch.delenv("HX_EMAIL_QQ_ENGINE_VERSION", raising=False)
    rid = default_asset_rid()
    expected = (
        "https://github.com/LagrangeDev/Lagrange.Core/releases/download/0.25.0/"
        f"Lagrange.OneBot_0.25.0_{rid}.zip"
    )
    asset_href = (
        f"/LagrangeDev/Lagrange.Core/releases/download/0.25.0/Lagrange.OneBot_0.25.0_{rid}.zip"
    )
    atom_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        '<entry><link rel="alternate" '
        'href="https://github.com/LagrangeDev/Lagrange.Core/releases/tag/0.25.0"/>'
        "</entry></feed>"
    )

    def fake_get(url: str, **kwargs: object) -> FakeDiscoveryPage:
        if "api.github.com" in url:
            return FakeDiscoveryPage(status_code=403)
        if "expanded_assets" in url:
            return FakeDiscoveryPage(text=f'<a href="{asset_href}">x</a>')
        if "releases.atom" in url:
            return FakeDiscoveryPage(text=atom_xml)
        return FakeDiscoveryPage(text="no release data here")

    monkeypatch.setattr("hx_email.server.messaging.impl.discovery.requests.get", fake_get)

    assert resolve_default_download_url() == expected


def test_resolve_default_download_url_discovery_failure_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import requests
    from hx_email.server.messaging.impl.discovery import resolve_default_download_url

    monkeypatch.delenv("HX_EMAIL_QQ_ENGINE_URL", raising=False)
    monkeypatch.delenv("HX_EMAIL_QQ_ENGINE_VERSION", raising=False)

    def fake_get(url: str, **kwargs: object) -> FakeGetResponse:
        raise requests.ConnectionError("github unreachable")

    def fake_head(url: str, **kwargs: object) -> FakeGetResponse:
        raise requests.ConnectionError("github unreachable")

    monkeypatch.setattr("hx_email.server.messaging.impl.discovery.requests.get", fake_get)
    monkeypatch.setattr("hx_email.server.messaging.impl.discovery.requests.head", fake_head)

    with pytest.raises(RuntimeError, match="无法获取 QQ 引擎最新版本"):
        resolve_default_download_url()


def test_asset_matches_accepts_tar_gz_and_zip() -> None:
    from hx_email.server.messaging.impl.discovery import _asset_matches

    assert (
        _asset_matches(
            "https://github.com/LagrangeDev/Lagrange.Core/releases/download/nightly/"
            "Lagrange.OneBot_linux-x64_net9.0_SelfContained.tar.gz",
            "linux-x64",
        )
        is True
    )
    assert (
        _asset_matches(
            "https://github.com/LagrangeDev/Lagrange.Core/releases/download/nightly/"
            "Lagrange.OneBot_osx-arm64_net9.0_SelfContained.tar.gz",
            "osx-arm64",
        )
        is True
    )
    assert (
        _asset_matches(
            "https://github.com/LagrangeDev/Lagrange.Core/releases/download/nightly/"
            "Lagrange.OneBot_win-x64_net9.0_SelfContained.zip",
            "win-x64",
        )
        is True
    )
    assert (
        _asset_matches(
            "https://github.com/LagrangeDev/Lagrange.Core/releases/download/0.25.0/"
            "Lagrange.OneBot_0.25.0_linux-x64.zip",
            "linux-x64",
        )
        is True
    )
    assert (
        _asset_matches(
            "https://github.com/LagrangeDev/Lagrange.Core/releases/download/nightly/"
            "Lagrange.OneBot_win-x64_net9.0_SelfContained.zip",
            "linux-x64",
        )
        is False
    )


def test_resolve_default_download_url_falls_back_to_nightly_tar_gz(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hx_email.server.messaging.impl.discovery import (
        default_asset_rid,
        resolve_default_download_url,
    )

    rid = default_asset_rid()
    ext = ".zip" if rid.startswith("win") else ".tar.gz"
    expected = (
        "https://github.com/LagrangeDev/Lagrange.Core/releases/download/nightly/"
        f"Lagrange.OneBot_{rid}_net9.0_SelfContained{ext}"
    )
    asset_href = (
        f"/LagrangeDev/Lagrange.Core/releases/download/nightly/"
        f"Lagrange.OneBot_{rid}_net9.0_SelfContained{ext}"
    )
    calls: list[str] = []

    def fake_get(url: str, **kwargs: object) -> FakeDiscoveryPage:
        calls.append(url)
        if "api.github.com" in url:
            return FakeDiscoveryPage(status_code=403)
        if "expanded_assets" in url:
            assert url.endswith("expanded_assets/nightly")
            return FakeDiscoveryPage(text=f'<a href="{asset_href}">x</a>')
        return FakeDiscoveryPage(text="no release data here")

    monkeypatch.setattr("hx_email.server.messaging.impl.discovery.requests.get", fake_get)

    assert resolve_default_download_url() == expected
    assert len(calls) == 2
    assert calls[1].endswith("expanded_assets/nightly")


def test_resolve_default_download_url_pinned_nightly_last_resort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import requests
    from hx_email.server.messaging.impl.discovery import (
        _pinned_nightly_urls,
        default_asset_rid,
        resolve_default_download_url,
    )

    rid = default_asset_rid()
    expected = _pinned_nightly_urls(rid)[0]
    head_calls: list[str] = []

    def fake_get(url: str, **kwargs: object) -> FakeGetResponse:
        raise requests.ConnectionError("github unreachable")

    def fake_head(url: str, **kwargs: object) -> FakeDiscoveryPage:
        head_calls.append(url)
        return FakeDiscoveryPage(status_code=200)

    monkeypatch.setattr("hx_email.server.messaging.impl.discovery.requests.get", fake_get)
    monkeypatch.setattr("hx_email.server.messaging.impl.discovery.requests.head", fake_head)

    assert resolve_default_download_url() == expected
    assert head_calls == [expected]


def test_default_asset_rid_detects_arm64(monkeypatch: pytest.MonkeyPatch) -> None:
    from hx_email.server.messaging.impl import discovery

    monkeypatch.setattr(discovery.sys, "platform", "linux")
    monkeypatch.setattr(discovery.platform, "machine", lambda: "aarch64")
    assert discovery.default_asset_rid() == "linux-arm64"

    monkeypatch.setattr(discovery.platform, "machine", lambda: "armv7l")
    assert discovery.default_asset_rid() == "linux-arm"

    monkeypatch.setattr(discovery.sys, "platform", "darwin")
    monkeypatch.setattr(discovery.platform, "machine", lambda: "arm64")
    assert discovery.default_asset_rid() == "osx-arm64"

    monkeypatch.setattr(discovery.platform, "machine", lambda: "x86_64")
    assert discovery.default_asset_rid() == "osx-x64"


def test_engine_qr_image_reads_file_or_none(tmp_path: Any) -> None:
    from hx_email.server.messaging.engine import QR_FILE_NAME, QQEngineManager

    settings = make_settings(tmp_path)
    manager = QQEngineManager(settings, instance_id=9)
    (manager._dir / "cache").mkdir(parents=True)
    (manager._dir / "cache" / QR_FILE_NAME).write_bytes(b"QRDATA")
    assert manager.qr_image() == b"QRDATA"
    assert QQEngineManager(settings, instance_id=10).qr_image() is None


def test_engine_refresh_qr_route(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    from hx_email.server.messaging.engine import QQEngineManager

    settings = make_settings(tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login(client, settings)
    instance = create_qq_instance(client, headers)

    monkeypatch.setattr(QQEngineManager, "refresh_qr", lambda self: None)
    response = client.post(
        f"{API}/messaging/instances/{instance['id']}/engine/refresh-qr", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

    def fake_refresh(self: QQEngineManager) -> None:
        raise RuntimeError("QQ 引擎未运行, 请先启动内置引擎")

    monkeypatch.setattr(QQEngineManager, "refresh_qr", fake_refresh)
    response = client.post(
        f"{API}/messaging/instances/{instance['id']}/engine/refresh-qr", headers=headers
    )
    assert response.status_code == 400
    assert "未运行" in response.json()["detail"]


def test_proxies_for_helper() -> None:
    from hx_email.server.messaging.impl.discovery import proxies_for

    assert proxies_for("") is None
    assert proxies_for("  ") is None
    assert proxies_for("http://127.0.0.1:7890") == {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890",
    }


def test_resolve_default_download_url_passes_proxy_to_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hx_email.server.messaging.impl.discovery import (
        default_asset_rid,
        resolve_default_download_url,
    )

    monkeypatch.delenv("HX_EMAIL_QQ_ENGINE_URL", raising=False)
    monkeypatch.delenv("HX_EMAIL_QQ_ENGINE_VERSION", raising=False)
    rid = default_asset_rid()
    expected = (
        "https://github.com/LagrangeDev/Lagrange.Core/releases/download/0.25.0/"
        f"Lagrange.OneBot_0.25.0_{rid}.zip"
    )
    captured: list[dict[str, object]] = []

    def fake_get(url: str, **kwargs: object) -> FakeDiscoveryPage:
        captured.append({"url": url, **kwargs})
        if "api.github.com" in url:
            return FakeDiscoveryPage(status_code=403)
        return FakeDiscoveryPage(text=f'"tag_name":"0.25.0" "browser_download_url":"{expected}"')

    monkeypatch.setattr("hx_email.server.messaging.impl.discovery.requests.get", fake_get)

    assert resolve_default_download_url(proxy_url="http://127.0.0.1:7890") == expected
    assert captured[0]["proxies"] == {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890",
    }
