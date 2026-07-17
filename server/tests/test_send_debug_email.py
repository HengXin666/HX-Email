from unittest.mock import patch

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate
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
            return_value=("access-token", "consumers"),
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
