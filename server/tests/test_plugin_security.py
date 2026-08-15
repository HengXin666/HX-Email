"""Plugin security regression tests: SSRF guard, no response echo, per-user config."""

from __future__ import annotations

import socket

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate

API = "/api/v1"


def login(client: TestClient, settings: Settings) -> dict[str, str]:
    session = client.post(
        f"{API}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    ).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def register_user(client: TestClient, username: str) -> dict[str, str]:
    session = client.post(
        f"{API}/auth/register",
        json={"username": username, "password": f"{username}-pass"},
    ).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def enable_registration(client: TestClient, settings: Settings) -> None:
    admin_headers = login(client, settings)
    client.put(
        "/api/v1/admin/settings/registration",
        json={"enabled": True},
        headers=admin_headers,
    )


def install_plugin(client: TestClient, headers: dict[str, str], name: str = "demo") -> None:
    response = client.post(
        f"{API}/plugins/install",
        json={"source": "https://example.com/plugin.zip", "name": name},
        headers=headers,
    )
    assert response.status_code == 200


class FakePluginSocket:
    def __init__(self, response: bytes) -> None:
        self._response: bytes = response
        self._offset: int = 0
        self.sent: bytes = b""

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def recv(self, size: int) -> bytes:
        chunk: bytes = self._response[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def close(self) -> None:
        pass


def test_plugin_test_connection_rejects_private_base_url(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login(client, settings)
    install_plugin(client, headers)
    client.post(
        f"{API}/plugins/demo/config",
        json={"config": {"api_base_url": "http://10.0.0.5:8080"}},
        headers=headers,
    )

    response = client.post(f"{API}/plugins/demo/test-connection", headers=headers)

    assert response.status_code == 400
    assert "仅允许公网地址" in response.json()["detail"]


def test_plugin_test_connection_rejects_metadata_base_url(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login(client, settings)
    install_plugin(client, headers)
    client.post(
        f"{API}/plugins/demo/config",
        json={"config": {"api_base_url": "http://169.254.169.254/latest/meta-data?x="}},
        headers=headers,
    )

    response = client.post(f"{API}/plugins/demo/test-connection", headers=headers)

    assert response.status_code == 400
    assert "仅允许公网地址" in response.json()["detail"]


def test_plugin_test_connection_does_not_echo_response_body(monkeypatch, tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login(client, settings)
    install_plugin(client, headers)
    client.post(
        f"{API}/plugins/demo/config",
        json={"config": {"api_base_url": "http://8.8.8.8:8080"}},
        headers=headers,
    )

    def fake_open(scheme: str, host: str, port: int, timeout: float) -> socket.socket:
        return FakePluginSocket(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n"
            b'{"secret-key":"top-secret-response"}'
        )

    monkeypatch.setattr("hx_email.server.plugins.open_plugin_socket", fake_open)

    response = client.post(f"{API}/plugins/demo/test-connection", headers=headers)

    assert response.status_code == 200
    assert response.json()["data"]["success"] is True
    assert "top-secret-response" not in response.text


def test_plugin_probe_revalidates_redirect_target(monkeypatch) -> None:
    from hx_email.server.plugins import probe_plugin_health

    first = FakePluginSocket(
        b"HTTP/1.1 302 Found\r\nLocation: http://192.168.1.10:8080/health\r\n\r\n"
    )

    def fake_open(scheme: str, host: str, port: int, timeout: float) -> socket.socket:
        if host == "public.example.com":
            return first
        raise ValueError("仅允许公网地址")

    monkeypatch.setattr("hx_email.server.plugins.open_plugin_socket", fake_open)

    result = probe_plugin_health("http://public.example.com")

    assert result["success"] is False
    assert "仅允许公网地址" in str(result["message"])


def test_plugin_probe_follows_public_redirect(monkeypatch) -> None:
    from hx_email.server.plugins import probe_plugin_health

    def fake_resolve(host: str) -> str:
        return {"public.example.com": "1.2.3.4", "cdn.example.com": "5.6.7.8"}[host]

    monkeypatch.setattr("hx_email.server.plugins.resolve_public_host", fake_resolve)

    def fake_open(scheme: str, host: str, port: int, timeout: float) -> socket.socket:
        if host == "public.example.com":
            return FakePluginSocket(
                b"HTTP/1.1 301 Moved Permanently\r\nLocation: http://cdn.example.com/health\r\n\r\n"
            )
        return FakePluginSocket(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")

    monkeypatch.setattr("hx_email.server.plugins.open_plugin_socket", fake_open)

    result = probe_plugin_health("http://public.example.com")

    assert result["success"] is True


def test_plugin_config_is_isolated_per_user(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    enable_registration(client, settings)
    alice_headers = register_user(client, "alice")
    bob_headers = register_user(client, "bob")
    install_plugin(client, alice_headers)

    saved = client.post(
        f"{API}/plugins/demo/config",
        json={"config": {"api_base_url": "http://8.8.8.8:8080", "api_key": "alice-secret"}},
        headers=alice_headers,
    )
    assert saved.status_code == 200

    alice_config = client.get(f"{API}/plugins/demo/config", headers=alice_headers).json()
    bob_config = client.get(f"{API}/plugins/demo/config", headers=bob_headers).json()

    assert alice_config["config"]["api_key"] == "alice-secret"
    assert bob_config["config"] == {}

    bob_test = client.post(f"{API}/plugins/demo/test-connection", headers=bob_headers)
    assert bob_test.status_code == 400
    assert "not configured" in bob_test.json()["detail"]


def test_plugin_uninstall_clears_only_own_config(tmp_path) -> None:
    from hx_email.database import connect

    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    enable_registration(client, settings)
    alice_headers = register_user(client, "alice")
    bob_headers = register_user(client, "bob")
    install_plugin(client, alice_headers)
    client.post(
        f"{API}/plugins/demo/config",
        json={"config": {"api_key": "alice-secret"}},
        headers=alice_headers,
    )

    assert client.post(f"{API}/plugins/demo/uninstall", headers=bob_headers).status_code == 200

    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT key FROM system_settings WHERE key LIKE 'plugin_config_%'"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0].endswith("_demo")
