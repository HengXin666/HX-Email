from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate
from hx_email.server.mail.email_accounts import add_email_account

API = "/api/v1"


def login_admin(client: TestClient, settings: Settings) -> dict[str, str]:
    session = client.post(
        f"{API}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    ).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def test_email_test_returns_message_when_smtp_fails(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)
    client.put(
        f"{API}/settings",
        json={
            "email_notification_smtp_host": "smtp.gmail.com",
            "email_notification_smtp_port": "587",
            "email_notification_smtp_user": "owner@gmail.com",
            "email_notification_smtp_password": "app-password",
        },
        headers=headers,
    )

    with patch("hx_email.server.mail.impl.sending.providers.smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value.starttls.side_effect = RuntimeError("TLS failed")
        response = client.post(
            f"{API}/settings/email-test",
            json={"recipient": "receiver@example.com"},
            headers=headers,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert "STARTTLS handshake" in payload["message"]
    assert "smtp.gmail.com:587" in payload["message"]


def test_email_test_uses_selected_account_credentials(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)
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

    with patch("hx_email.server.mail.impl.sending.providers.smtplib.SMTP") as smtp:
        response = client.post(
            f"{API}/settings/email-test",
            json={
                "recipient": "archive@example.com",
                "email_account_id": account.id,
            },
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Test email sent to archive@example.com",
    }
    smtp.return_value.__enter__.return_value.login.assert_called_once_with(
        "sender@example.com", "app-password"
    )


def test_email_test_uses_smtp_override_with_custom_account_credentials(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)
    account = add_email_account(
        settings,
        1,
        "custom",
        "sender@example.com",
        "Sender",
        "imap.custom.example",
        993,
        "sender@example.com",
        "app-password",
    )

    with (
        patch("hx_email.server.mail.impl.sending.providers.smtplib.SMTP_SSL") as smtp_ssl,
        patch("hx_email.server.mail.impl.sending.providers.smtplib.SMTP") as smtp,
    ):
        response = client.post(
            f"{API}/settings/email-test",
            json={
                "recipient": "archive@example.com",
                "email_account_id": account.id,
                "smtp_host": "smtp.custom.example",
                "smtp_port": 465,
            },
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Test email sent to archive@example.com",
    }
    smtp_ssl.assert_called_once_with("smtp.custom.example", 465, timeout=15)
    smtp.assert_not_called()
    smtp_ssl.return_value.__enter__.return_value.login.assert_called_once_with(
        "sender@example.com", "app-password"
    )
