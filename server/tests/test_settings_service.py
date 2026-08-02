import json
from pathlib import Path

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate
from hx_email.server.mail.email_accounts import add_email_account
from hx_email.server.settings_service import set_setting

API_PREFIX = "/api/v1"


def login_admin(client: TestClient, settings: Settings) -> dict[str, str]:
    response = client.post(
        f"{API_PREFIX}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    )
    token: str = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_settings_accept_external_api_keys_as_json_array(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    with TestClient(create_app(settings)) as client:
        headers = login_admin(client, settings)
        response = client.put(
            f"{API_PREFIX}/settings",
            json={"external_api_keys": ["key-one", "key-two"]},
            headers=headers,
        )

    assert response.status_code == 200
    assert json.loads(response.json()["external_api_keys"]) == ["key-one", "key-two"]


def test_settings_normalize_external_api_keys_json_string_and_batch_save(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    with TestClient(create_app(settings)) as client:
        headers = login_admin(client, settings)
        first_response = client.put(
            f"{API_PREFIX}/settings",
            json={"external_api_keys": ' ["key-one", "key-two"] '},
            headers=headers,
        )
        saved_settings: dict[str, str] = first_response.json()
        saved_settings["email_notification_smtp_host"] = "smtp.example.com"
        second_response = client.put(
            f"{API_PREFIX}/settings",
            json=saved_settings,
            headers=headers,
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json()["email_notification_smtp_host"] == "smtp.example.com"
    assert second_response.json()["external_api_keys"] == '["key-one", "key-two"]'


def test_settings_migrate_legacy_external_api_key_map_during_batch_save(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    with TestClient(create_app(settings)) as client:
        headers = login_admin(client, settings)
        legacy_settings = client.get(f"{API_PREFIX}/settings", headers=headers).json()
        legacy_settings["external_api_keys"] = '{"primary": "key-one", "backup": "key-two"}'
        legacy_settings["email_notification_smtp_host"] = "smtp.example.com"
        response = client.put(
            f"{API_PREFIX}/settings",
            json=legacy_settings,
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json()["external_api_keys"] == '["key-one", "key-two"]'


def test_get_settings_exposes_legacy_external_api_keys_as_array(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    set_setting(settings, "external_api_keys", '{"primary": "key-one"}')
    with TestClient(create_app(settings)) as client:
        headers = login_admin(client, settings)
        response = client.get(f"{API_PREFIX}/settings", headers=headers)

    assert response.status_code == 200
    assert response.json()["external_api_keys"] == '["key-one"]'


def test_settings_reject_external_api_keys_that_are_not_string_arrays(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    with TestClient(create_app(settings)) as client:
        headers = login_admin(client, settings)
        invalid_values: list[object] = [
            {"key": 2},
            ["key-one", 2],
            "not-json",
        ]
        responses = [
            client.put(
                f"{API_PREFIX}/settings",
                json={"external_api_keys": value},
                headers=headers,
            )
            for value in invalid_values
        ]

    assert [response.status_code for response in responses] == [422, 422, 422]


def test_email_forwarding_can_use_an_owned_account_without_manual_smtp(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    account = add_email_account(
        settings,
        1,
        "qq",
        "sender@example.com",
        "Sender",
        "imap.qq.com",
        993,
        "sender@example.com",
        "app-password",
    )
    with TestClient(create_app(settings)) as client:
        headers = login_admin(client, settings)
        response = client.put(
            f"{API_PREFIX}/settings",
            json={
                "email_notification_enabled": "true",
                "email_notification_recipient": "archive@example.com",
                "email_notification_account_id": str(account.id),
            },
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json()["email_notification_account_id"] == str(account.id)


def test_email_forwarding_rejects_an_account_owned_by_another_user(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    account = add_email_account(
        settings,
        2,
        "qq",
        "other@example.com",
        "Other",
        "imap.qq.com",
        993,
        "other@example.com",
        "app-password",
    )
    with TestClient(create_app(settings)) as client:
        headers = login_admin(client, settings)
        response = client.put(
            f"{API_PREFIX}/settings",
            json={
                "email_notification_enabled": "true",
                "email_notification_recipient": "archive@example.com",
                "email_notification_account_id": str(account.id),
            },
            headers=headers,
        )

    assert response.status_code == 422
    assert "owned by you" in response.json()["detail"]
