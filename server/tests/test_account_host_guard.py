"""Email account IMAP host guard: reserved/metadata hosts always rejected.

Private (RFC1918) hosts are accepted by default for self-hosted LAN mail
servers and rejected again in strict mode (HX_EMAIL_ALLOW_PRIVATE_PROXY=false).
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate

API = "/api/v1"


def login_admin(client: TestClient, settings: Settings) -> dict[str, str]:
    session = client.post(
        f"{API}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    ).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def create_account(
    client: TestClient, headers: dict[str, str], imap_host: str, address: str = "owner@example.com"
) -> dict[str, object]:
    return client.post(
        f"{API}/email-accounts",
        json={
            "provider": "imap",
            "primary_address": address,
            "display_name": "Owner",
            "imap_host": imap_host,
            "imap_port": 993,
            "username": address,
        },
        headers=headers,
    ).json()


def test_create_account_allows_private_imap_host_by_default(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)

    for host in ["10.0.0.5", "192.168.1.1", "172.16.0.1"]:
        response = client.post(
            f"{API}/email-accounts",
            json={
                "provider": "imap",
                "primary_address": f"owner-{host}@example.com",
                "display_name": "Owner",
                "imap_host": host,
                "imap_port": 993,
                "username": "owner",
            },
            headers=headers,
        )
        assert response.status_code == 201


def test_create_account_rejects_metadata_imap_host(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)

    response = client.post(
        f"{API}/email-accounts",
        json={
            "provider": "imap",
            "primary_address": "owner@example.com",
            "display_name": "Owner",
            "imap_host": "169.254.169.254",
            "imap_port": 993,
            "username": "owner",
        },
        headers=headers,
    )
    assert response.status_code == 422
    assert "不允许" in response.json()["detail"]


def test_create_account_rejects_private_imap_host_in_strict_mode(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        admin_username="admin",
        admin_password="admin",
        allow_private_proxy=False,
    )
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)

    for host in ["10.0.0.5", "192.168.1.1", "172.16.0.1", "169.254.169.254"]:
        response = client.post(
            f"{API}/email-accounts",
            json={
                "provider": "imap",
                "primary_address": f"owner-{host}@example.com",
                "display_name": "Owner",
                "imap_host": host,
                "imap_port": 993,
                "username": "owner",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "不允许" in response.json()["detail"]


def test_create_account_accepts_loopback_and_public_hosts(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)

    for host, address in [("127.0.0.1", "a@example.com"), ("8.8.8.8", "b@example.com")]:
        response = client.post(
            f"{API}/email-accounts",
            json={
                "provider": "imap",
                "primary_address": address,
                "display_name": "Owner",
                "imap_host": host,
                "imap_port": 993,
                "username": address,
            },
            headers=headers,
        )
        assert response.status_code == 201


def test_update_account_rejects_metadata_imap_host(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)
    created = create_account(client, headers, "8.8.8.8")

    response = client.put(
        f"{API}/email-accounts/{created['id']}",
        json={"imap_host": "169.254.169.254"},
        headers=headers,
    )

    assert response.status_code == 422
    assert "不允许" in response.json()["detail"]


def test_update_account_rejects_private_imap_host_in_strict_mode(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        admin_username="admin",
        admin_password="admin",
        allow_private_proxy=False,
    )
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)
    created = create_account(client, headers, "8.8.8.8")

    response = client.put(
        f"{API}/email-accounts/{created['id']}",
        json={"imap_host": "192.168.1.1"},
        headers=headers,
    )

    assert response.status_code == 422
    assert "不允许" in response.json()["detail"]


def test_import_rejects_metadata_custom_host_per_line(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)

    response = client.post(
        f"{API}/email-accounts/import",
        json={
            "provider": "auto",
            "text": "\n".join(
                [
                    "good@example.com----pass----custom----8.8.8.8----993",
                    "bad@example.com----pass----custom----169.254.169.254----993",
                ]
            ),
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["imported"] == 1
    assert response.json()["failed"] == 1
    assert "不允许" in response.json()["errors"][0]["error"]


def test_import_rejects_private_custom_host_per_line_in_strict_mode(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        admin_username="admin",
        admin_password="admin",
        allow_private_proxy=False,
    )
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)

    response = client.post(
        f"{API}/email-accounts/import",
        json={
            "provider": "auto",
            "text": "\n".join(
                [
                    "good@example.com----pass----custom----8.8.8.8----993",
                    "bad@example.com----pass----custom----10.0.0.5----993",
                ]
            ),
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["imported"] == 1
    assert response.json()["failed"] == 1
    assert "不允许" in response.json()["errors"][0]["error"]


def test_import_rejects_metadata_fallback_custom_host(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)

    response = client.post(
        f"{API}/email-accounts/import",
        json={
            "provider": "custom",
            "custom_imap_host": "169.254.169.254",
            "custom_imap_port": 993,
            "text": "user@unknown-domain.example----app-pass",
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["failed"] == 1
    assert "不允许" in response.json()["errors"][0]["error"]
