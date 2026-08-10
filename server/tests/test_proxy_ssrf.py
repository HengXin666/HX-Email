"""Regression tests: proxy targets must not reach private/reserved networks."""

import socket
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate
from hx_email.server.mail.imap.impl.address_guard import (
    validate_proxy_endpoint,
    validate_proxy_host,
)
from hx_email.server.mail.imap.impl.proxy import http_connect_via_proxy

API = "/api/v1"


def login_admin(client: TestClient, settings: Settings) -> dict[str, str]:
    session = client.post(
        f"{API}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    ).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def test_proxy_validation_rejects_private_and_reserved_addresses() -> None:
    for proxy_url in [
        "http://127.0.0.1:8080",
        "10.0.0.5:3128",
        "192.168.1.1:8080",
        "http://172.16.0.1:3128",
        "169.254.169.254:80",
        "http://0.0.0.0:8080",
        "100.64.0.1:8080",
        "http://[::1]:8080",
        "http://[fe80::1]:8080",
        "http://[fc00::1]:8080",
    ]:
        with pytest.raises(ValueError):
            validate_proxy_endpoint(proxy_url)


def test_proxy_validation_allows_public_addresses() -> None:
    assert validate_proxy_endpoint("http://8.8.8.8:8080") == ("8.8.8.8", 8080)
    assert validate_proxy_endpoint("1.1.1.1:3128") == ("1.1.1.1", 3128)


def test_proxy_validation_rejects_hostname_resolving_to_private(monkeypatch) -> None:
    monkeypatch.setattr(
        "hx_email.server.mail.imap.impl.address_guard.socket.getaddrinfo",
        lambda host, port: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0))],
    )
    with pytest.raises(ValueError):
        validate_proxy_host("metadata.internal")


def test_proxy_validation_allows_hostname_resolving_to_public(monkeypatch) -> None:
    monkeypatch.setattr(
        "hx_email.server.mail.imap.impl.address_guard.socket.getaddrinfo",
        lambda host, port: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0))],
    )
    assert validate_proxy_host("proxy.example.com") == "proxy.example.com"


def test_proxy_test_endpoint_rejects_private_proxy(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)

    response = client.post(
        f"{API}/groups/proxy-test",
        json={"proxy_url": "http://169.254.169.254:80"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "不允许" in response.json()["message"]


class FakeProxySocket:
    def sendall(self, _data: bytes) -> None:
        pass

    def recv(self, _size: int) -> bytes:
        return b"HTTP/1.1 200 Connection Established\r\n\r\n"

    def close(self) -> None:
        pass


def test_proxy_test_endpoint_connects_to_public_proxy(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)

    with patch(
        "hx_email.api.impl.workspace_routes.socket.create_connection",
        return_value=FakeProxySocket(),
    ) as create_connection:
        response = client.post(
            f"{API}/groups/proxy-test",
            json={"proxy_url": "http://8.8.8.8:8080"},
            headers=headers,
        )
    assert response.status_code == 200
    assert response.json()["success"] is True
    create_connection.assert_called_once_with(("8.8.8.8", 8080), timeout=10)


def test_group_create_rejects_private_proxy_url(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)

    rejected = client.post(
        f"{API}/groups",
        json={"name": "Bad", "proxy_url": "http://192.168.1.1:8080"},
        headers=headers,
    )
    assert rejected.status_code == 400
    accepted = client.post(
        f"{API}/groups",
        json={"name": "Good", "proxy_url": "http://8.8.8.8:8080"},
        headers=headers,
    )
    assert accepted.status_code == 201


def test_http_connect_via_proxy_rejects_private_proxy() -> None:
    with (
        patch("hx_email.server.mail.imap.impl.proxy.socket.create_connection") as create_connection,
        pytest.raises(ValueError),
    ):
        http_connect_via_proxy("http://127.0.0.1:2334", "smtp.gmail.com", 587)
    create_connection.assert_not_called()
