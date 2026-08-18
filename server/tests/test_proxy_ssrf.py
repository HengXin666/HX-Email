"""Regression tests: proxy targets must never reach reserved/metadata networks.

Private (RFC1918/ULA) ranges are allowed by default for self-hosted LAN proxies
and rejected again in strict mode (HX_EMAIL_ALLOW_PRIVATE_PROXY=false).
"""

import socket
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate
from hx_email.server.mail.imap.impl.address_guard import (
    resolve_proxy_host,
    set_private_proxy_policy,
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


def test_proxy_validation_allows_loopback_and_docker_gateway_hosts() -> None:
    """Whitelist: loopback plus the Docker gateway hostname stay allowed."""
    for proxy_url in ["http://127.0.0.1:8080", "http://[::1]:8080"]:
        validate_proxy_endpoint(proxy_url)


def test_proxy_validation_allows_private_addresses_by_default() -> None:
    """Self-hosted default: RFC1918/ULA private ranges are usable proxies."""
    for proxy_url in [
        "10.0.0.5:3128",
        "192.168.1.1:8080",
        "http://172.16.0.1:3128",
        "http://[fc00::1]:8080",
        "http://[::ffff:10.0.0.1]:3128",
    ]:
        validate_proxy_endpoint(proxy_url)


def test_proxy_validation_rejects_private_addresses_in_strict_mode() -> None:
    """Strict mode (HX_EMAIL_ALLOW_PRIVATE_PROXY=false) blocks RFC1918/ULA again."""
    set_private_proxy_policy(False)
    for proxy_url in [
        "10.0.0.5:3128",
        "192.168.1.1:8080",
        "http://172.16.0.1:3128",
        "http://[fc00::1]:8080",
        "http://[::ffff:10.0.0.1]:3128",
    ]:
        with pytest.raises(ValueError):
            validate_proxy_endpoint(proxy_url)


def test_proxy_validation_rejects_metadata_and_reserved_addresses() -> None:
    for proxy_url in [
        "169.254.169.254:80",
        "http://0.0.0.0:8080",
        "100.64.0.1:8080",
        "http://[fe80::1]:8080",
    ]:
        with pytest.raises(ValueError):
            validate_proxy_endpoint(proxy_url)


def test_proxy_validation_allows_public_addresses() -> None:
    assert validate_proxy_endpoint("http://8.8.8.8:8080") == ("8.8.8.8", 8080)
    assert validate_proxy_endpoint("1.1.1.1:3128") == ("1.1.1.1", 3128)


def test_proxy_validation_judges_ipv4_mapped_ipv6_by_embedded_ipv4() -> None:
    for proxy_url in [
        "http://[::ffff:127.0.0.1]:8080",
        "http://[::ffff:8.8.8.8]:8080",
        "http://[::ffff:10.0.0.1]:3128",
    ]:
        validate_proxy_endpoint(proxy_url)
    for proxy_url in [
        "http://[::ffff:169.254.169.254]:80",
        "http://[64:ff9b::a00:1]:8080",
    ]:
        with pytest.raises(ValueError):
            validate_proxy_endpoint(proxy_url)
    set_private_proxy_policy(False)
    with pytest.raises(ValueError):
        validate_proxy_endpoint("http://[::ffff:10.0.0.1]:3128")


def test_proxy_validation_rejects_tunnel_and_nat64_ipv6() -> None:
    for proxy_url in [
        "http://[64:ff9b:1::7f00:1]:8080",
        "http://[64:ff9b:1::a00:1]:3128",
        "http://[2002:7f00:1::1]:8080",
        "http://[2002:a00:1::1]:3128",
        "http://[2001::1]:8080",
        "http://[100::1]:8080",
    ]:
        with pytest.raises(ValueError):
            validate_proxy_endpoint(proxy_url)


def test_proxy_validation_allows_public_ipv6() -> None:
    assert validate_proxy_endpoint("http://[2606:4700::1111]:8080") == (
        "2606:4700::1111",
        8080,
    )
    assert validate_proxy_endpoint("http://[2001:4860:4860::8888]:8080") == (
        "2001:4860:4860::8888",
        8080,
    )


def test_proxy_validation_rejects_hostname_resolving_to_private(monkeypatch) -> None:
    monkeypatch.setattr(
        "hx_email.server.mail.imap.impl.address_guard.socket.getaddrinfo",
        lambda host, port: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))],
    )
    with pytest.raises(ValueError):
        validate_proxy_host("metadata.internal")


def test_proxy_validation_allows_docker_host_resolving_to_private_gateway(monkeypatch) -> None:
    """host.docker.internal resolves to a private bridge gateway and must stay allowed."""
    monkeypatch.setattr(
        "hx_email.server.mail.imap.impl.address_guard.socket.getaddrinfo",
        lambda host, port: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.17.0.1", 0))],
    )
    assert validate_proxy_host("host.docker.internal") == "host.docker.internal"
    assert resolve_proxy_host("host.docker.internal") == "172.17.0.1"


def test_proxy_validation_allows_hostname_resolving_to_private_by_default(monkeypatch) -> None:
    """A hostname resolving to a private LAN address stays usable by default."""
    monkeypatch.setattr(
        "hx_email.server.mail.imap.impl.address_guard.socket.getaddrinfo",
        lambda host, port: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.9", 0))],
    )
    assert validate_proxy_host("proxy.internal") == "proxy.internal"
    assert resolve_proxy_host("proxy.internal") == "10.0.0.9"


def test_proxy_validation_rejects_hostname_resolving_to_private_in_strict_mode(monkeypatch) -> None:
    """Strict mode rejects hostnames resolving into RFC1918 private ranges."""
    set_private_proxy_policy(False)
    monkeypatch.setattr(
        "hx_email.server.mail.imap.impl.address_guard.socket.getaddrinfo",
        lambda host, port: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.9", 0))],
    )
    with pytest.raises(ValueError):
        validate_proxy_host("proxy.internal")


def test_proxy_validation_allows_hostname_resolving_to_public(monkeypatch) -> None:
    monkeypatch.setattr(
        "hx_email.server.mail.imap.impl.address_guard.socket.getaddrinfo",
        lambda host, port: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0))],
    )
    assert validate_proxy_host("proxy.example.com") == "proxy.example.com"


def test_resolve_proxy_host_pins_resolved_ip(monkeypatch) -> None:
    monkeypatch.setattr(
        "hx_email.server.mail.imap.impl.address_guard.socket.getaddrinfo",
        lambda host, port: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.4.4", 0)),
        ],
    )
    assert resolve_proxy_host("proxy.example.com") == "8.8.8.8"


def test_resolve_proxy_host_rejects_any_metadata_resolved_address(monkeypatch) -> None:
    """Metadata/link-local addresses stay blocked even in the default policy."""
    monkeypatch.setattr(
        "hx_email.server.mail.imap.impl.address_guard.socket.getaddrinfo",
        lambda host, port: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0)),
        ],
    )
    with pytest.raises(ValueError):
        resolve_proxy_host("proxy.example.com")


def test_resolve_proxy_host_rejects_private_resolved_in_strict_mode(monkeypatch) -> None:
    """Strict mode rejects hostnames resolving to any private address."""
    set_private_proxy_policy(False)
    monkeypatch.setattr(
        "hx_email.server.mail.imap.impl.address_guard.socket.getaddrinfo",
        lambda host, port: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.9", 0)),
        ],
    )
    with pytest.raises(ValueError):
        resolve_proxy_host("proxy.example.com")


def test_http_connect_via_proxy_connects_to_pinned_ip(monkeypatch) -> None:
    resolutions: list[str] = []

    def fake_getaddrinfo(host: str, port: int) -> list:
        resolutions.append(host)
        if len(resolutions) == 1:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 0))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]

    monkeypatch.setattr(
        "hx_email.server.mail.imap.impl.address_guard.socket.getaddrinfo",
        fake_getaddrinfo,
    )
    with patch(
        "hx_email.server.mail.imap.impl.proxy.socket.create_connection"
    ) as create_connection:
        create_connection.return_value = FakeProxySocket()
        http_connect_via_proxy("http://proxy.example.com:2334", "smtp.gmail.com", 587)
    create_connection.assert_called_once_with(("8.8.8.8", 2334), timeout=30)
    assert resolutions == ["proxy.example.com"]


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


def test_group_create_rejects_metadata_proxy_and_accepts_local_proxy(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)

    rejected = client.post(
        f"{API}/groups",
        json={"name": "Bad", "proxy_url": "http://169.254.169.254:80"},
        headers=headers,
    )
    assert rejected.status_code == 400
    accepted = client.post(
        f"{API}/groups",
        json={"name": "Good", "proxy_url": "http://8.8.8.8:8080"},
        headers=headers,
    )
    assert accepted.status_code == 201
    local = client.post(
        f"{API}/groups",
        json={"name": "Local", "proxy_url": "http://127.0.0.1:7890"},
        headers=headers,
    )
    assert local.status_code == 201
    lan = client.post(
        f"{API}/groups",
        json={"name": "Lan", "proxy_url": "http://192.168.1.50:7890"},
        headers=headers,
    )
    assert lan.status_code == 201


def test_group_create_rejects_private_proxy_in_strict_mode(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        admin_username="admin",
        admin_password="admin",
        allow_private_proxy=False,
    )
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)

    rejected = client.post(
        f"{API}/groups",
        json={"name": "Lan", "proxy_url": "http://192.168.1.50:7890"},
        headers=headers,
    )
    assert rejected.status_code == 400
    assert "不允许" in rejected.json()["detail"]


def test_http_connect_via_proxy_rejects_metadata_proxy() -> None:
    with (
        patch("hx_email.server.mail.imap.impl.proxy.socket.create_connection") as create_connection,
        pytest.raises(ValueError),
    ):
        http_connect_via_proxy("http://169.254.169.254:80", "smtp.gmail.com", 587)
    create_connection.assert_not_called()
