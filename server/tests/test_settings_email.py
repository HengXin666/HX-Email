from unittest.mock import patch

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

    with patch("hx_email.api.impl.settings.settings_test_routes.smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value.starttls.side_effect = RuntimeError("TLS failed")
        response = client.post(
            f"{API}/settings/email-test",
            json={"recipient": "receiver@example.com"},
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json() == {"success": False, "message": "TLS failed"}
