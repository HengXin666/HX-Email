from unittest.mock import patch

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.security import decrypt_secret
from hx_email.server.mail.email_accounts import add_email_account

API = "/api/v1"


def login_admin(client: TestClient, settings: Settings) -> dict[str, str]:
    session: dict[str, str] = client.post(
        f"{API}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    ).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def test_send_debug_email_route_uses_account_smtp_credentials(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)
    account = add_email_account(
        settings,
        1,
        "gmail",
        "sender@gmail.com",
        "Sender",
        "imap.gmail.com",
        993,
        "sender@gmail.com",
        "gmail-app-pass",
    )

    with patch("hx_email.server.mail.impl.sending.providers.smtplib.SMTP") as smtp:
        response = client.post(
            f"{API}/usable-emails/{account.primary_usable_email.id}/send-debug-email",
            json={
                "recipient": "receiver@example.com",
                "subject": "Debug",
                "body": "Hello",
            },
            headers=headers,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["code"] == "sent"
    assert payload["smtp_host"] == "smtp.gmail.com"
    smtp.assert_called_once_with("smtp.gmail.com", 587, timeout=15)
    smtp.return_value.__enter__.return_value.login.assert_called_once_with(
        "sender@gmail.com", "gmail-app-pass"
    )
    smtp.return_value.__enter__.return_value.send_message.assert_called_once()


def test_send_debug_email_uses_xoauth2_for_gmail_oauth_credentials(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)
    account = add_email_account(
        settings,
        1,
        "gmail",
        "sender@gmail.com",
        "Sender",
        "imap.gmail.com",
        993,
        "sender@gmail.com",
        "",
        "google-client-id",
        "google-refresh-token",
    )

    with (
        patch(
            "hx_email.server.mail.impl.sending.delivery.get_google_access_token",
            return_value="google-access-token",
        ) as access_token,
        patch("hx_email.server.mail.impl.sending.providers.smtplib.SMTP") as smtp,
    ):
        connection = smtp.return_value.__enter__.return_value
        connection.docmd.return_value = (235, b"2.7.0 Accepted")
        response = client.post(
            f"{API}/usable-emails/{account.primary_usable_email.id}/send-debug-email",
            json={
                "recipient": "receiver@example.com",
                "subject": "Debug",
                "body": "Hello",
            },
            headers=headers,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["credential_strategy"] == "gmail_oauth_smtp"
    access_token.assert_called_once()
    connection.login.assert_not_called()
    connection.docmd.assert_called_once()
    auth_command = connection.docmd.call_args.args
    assert auth_command[0] == "AUTH"
    assert auth_command[1].startswith("XOAUTH2 ")
    connection.send_message.assert_called_once()


def test_send_debug_email_uses_selected_alias_from_address(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)
    account = add_email_account(
        settings,
        1,
        "gmail",
        "sender@gmail.com",
        "Sender",
        "imap.gmail.com",
        993,
        "sender@gmail.com",
        "gmail-app-pass",
        alias_addresses=["alias@gmail.com"],
    )
    alias = next(email for email in account.usable_emails if email.kind == "alias")

    with patch("hx_email.server.mail.impl.sending.providers.smtplib.SMTP") as smtp:
        response = client.post(
            f"{API}/usable-emails/{alias.id}/send-debug-email",
            json={
                "recipient": "receiver@example.com",
                "subject": "Debug",
                "body": "Hello",
            },
            headers=headers,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["from_address"] == "alias@gmail.com"
    smtp.return_value.__enter__.return_value.login.assert_called_once_with(
        "sender@gmail.com", "gmail-app-pass"
    )
    message = smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
    assert message["From"] == "alias@gmail.com"


def test_send_debug_email_returns_guidance_when_credentials_are_missing(tmp_path) -> None:
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
        "",
        993,
        "sender@example.com",
        "",
    )

    response = client.post(
        f"{API}/usable-emails/{account.primary_usable_email.id}/send-debug-email",
        json={"recipient": "receiver@example.com", "subject": "Debug", "body": "Hello"},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["code"] == "missing_smtp_host"
    assert payload["actions"]


def test_send_debug_email_uses_graph_for_outlook_oauth_credentials(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)
    account = add_email_account(
        settings,
        1,
        "outlook",
        "sender@outlook.com",
        "Sender",
        "",
        993,
        "sender@outlook.com",
        "",
        "client-id",
        "refresh-token",
    )

    with (
        patch(
            "hx_email.server.mail.graph.graph_helpers.try_get_graph_token",
            return_value=("access-token", "consumers", "rotated-refresh-token"),
        ) as token,
        patch("hx_email.server.mail.graph.graph_helpers.requests.post") as post,
    ):
        post.return_value.status_code = 202
        response = client.post(
            f"{API}/usable-emails/{account.primary_usable_email.id}/send-debug-email",
            json={
                "recipient": "",
                "subject": "Debug",
                "body": "Hello",
            },
            headers=headers,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["code"] == "sent"
    assert payload["to_address"] == "sender@outlook.com"
    assert payload["credential_strategy"] == "outlook_graph_send_mail"
    token.assert_called_once()
    post.assert_called_once()
    request_body = post.call_args.kwargs["json"]
    assert request_body["message"]["subject"] == "Debug"
    assert request_body["message"]["toRecipients"][0]["emailAddress"]["address"] == (
        "sender@outlook.com"
    )
    with connect(settings) as connection:
        stored: str = str(
            connection.execute(
                "SELECT refresh_token FROM email_accounts WHERE id = ?", (account.id,)
            ).fetchone()["refresh_token"]
        )
    assert decrypt_secret(settings, stored) == "rotated-refresh-token"


def test_outlook_send_failure_explains_mail_send_reauthorization(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)
    account = add_email_account(
        settings,
        1,
        "outlook",
        "sender@outlook.com",
        "Sender",
        "",
        993,
        "sender@outlook.com",
        "",
        "client-id",
        "refresh-token",
    )

    with patch(
        "hx_email.server.mail.graph.graph_helpers.try_get_graph_token",
        side_effect=RuntimeError("AADSTS65001: consent required"),
    ):
        response = client.post(
            f"{API}/usable-emails/{account.primary_usable_email.id}/send-debug-email",
            json={"recipient": "receiver@example.com", "subject": "Debug", "body": "Hello"},
            headers=headers,
        )

    payload = response.json()
    assert payload["success"] is False
    assert payload["code"] == "delivery_failed"
    assert any("Mail.Send" in action for action in payload["actions"])
    assert any("重新授权" in action for action in payload["actions"])
