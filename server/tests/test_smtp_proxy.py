from email.message import EmailMessage
from pathlib import Path
from unittest.mock import patch

from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.mail.imap.impl.proxy import http_connect_via_proxy
from hx_email.server.mail.impl.sending.credentials import SendCredentials
from hx_email.server.mail.impl.sending.delivery import deliver_debug_email
from hx_email.server.mail.impl.sending.providers import SmtpEmailServerBase
from hx_email.server.notifications.impl.channels import send_delivery
from hx_email.server.notifications.models import StoredMessageEvent
from hx_email.server.settings_service import set_setting


def create_proxy_account(settings: Settings) -> None:
    with connect(settings) as connection:
        connection.execute(
            "INSERT INTO groups (id, user_id, name, proxy_url)"
            " VALUES (10, 1, 'Proxy', 'http://127.0.0.1:2334')"
        )
        connection.execute(
            "INSERT INTO email_accounts"
            " (id, user_id, provider, primary_address, group_id)"
            " VALUES (1, 1, 'qq', 'sender@example.com', 10)"
        )


def test_smtp_account_delivery_passes_group_proxy(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    create_proxy_account(settings)
    credentials = SendCredentials(
        usable_email_id=0,
        email_account_id=1,
        provider="qq",
        from_address="sender@example.com",
        username="sender@example.com",
        password="app-password",
        client_id="",
        refresh_token="",
        smtp_host="smtp.qq.com",
        smtp_port=587,
        security="starttls",
        credential_strategy="email_account_smtp_password",
    )

    with (
        patch("hx_email.server.mail.impl.sending.delivery.deliver_smtp_message") as deliver,
        patch(
            "hx_email.server.mail.impl.sending.delivery.load_group_proxy",
            return_value="http://127.0.0.1:2334",
        ) as load_proxy,
    ):
        deliver_debug_email(settings, credentials, "archive@example.com", "Subject", "Body")

    load_proxy.assert_called_once_with(settings, 1)
    assert deliver.call_args.kwargs["proxy_url"] == "http://127.0.0.1:2334"


def test_starttls_delivery_uses_proxy_smtp_client() -> None:
    credentials = SendCredentials(
        usable_email_id=0,
        email_account_id=1,
        provider="qq",
        from_address="sender@example.com",
        username="sender@example.com",
        password="app-password",
        client_id="",
        refresh_token="",
        smtp_host="smtp.qq.com",
        smtp_port=587,
        security="starttls",
        credential_strategy="email_account_smtp_password",
    )
    message = EmailMessage()

    with patch("hx_email.server.mail.impl.sending.providers.SmtpProxyClient") as proxy_client:
        SmtpEmailServerBase().deliver(
            credentials,
            message,
            proxy_url="http://127.0.0.1:2334",
        )

    proxy_client.assert_called_once_with(
        "smtp.qq.com",
        587,
        "http://127.0.0.1:2334",
        timeout=15,
    )
    smtp_client = proxy_client.return_value.__enter__.return_value
    smtp_client.starttls.assert_called_once_with()
    smtp_client.login.assert_called_once_with("sender@example.com", "app-password")
    smtp_client.send_message.assert_called_once_with(message)


class FakeProxySocket:
    def __init__(self) -> None:
        self.sent: list[bytes] = []

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)

    def recv(self, _size: int) -> bytes:
        return b"HTTP/1.1 200 Connection Established\r\n\r\n"

    def close(self) -> None:
        pass


def test_http_connect_proxy_tunnels_to_smtp_target() -> None:
    proxy_socket = FakeProxySocket()
    with patch(
        "hx_email.server.mail.imap.impl.proxy.socket.create_connection",
        return_value=proxy_socket,
    ) as create_connection:
        result = http_connect_via_proxy(
            "http://8.8.8.8:2334",
            "smtp.gmail.com",
            587,
            timeout=15,
        )

    assert result is proxy_socket
    create_connection.assert_called_once_with(("8.8.8.8", 2334), timeout=15)
    assert proxy_socket.sent == [
        b"CONNECT smtp.gmail.com:587 HTTP/1.1\r\nHost: smtp.gmail.com:587\r\n\r\n"
    ]


def test_manual_forwarding_does_not_use_monitored_account_group_proxy(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    create_proxy_account(settings)
    set_setting(settings, "email_notification_recipient", "archive@example.com")
    set_setting(settings, "email_notification_smtp_host", "smtp.gmail.com")
    set_setting(settings, "email_notification_smtp_user", "sender@example.com")
    set_setting(settings, "email_notification_smtp_password", "app-password")
    event = StoredMessageEvent(
        id=1,
        user_id=1,
        usable_email_id=1,
        email_account_id=1,
        address="sender@example.com",
        group_id=10,
        group_name="Proxy",
        email_notify_enabled=True,
        group_notify_enabled=True,
        account_telegram_enabled=True,
        from_address="source@example.com",
        recipient_address="sender@example.com",
        subject="Subject",
        body="Body",
        received_at="2026-08-01T10:00:00Z",
    )

    with patch("hx_email.server.notifications.impl.channels.deliver_smtp_email") as deliver:
        send_delivery(settings, event, "email")

    assert deliver.call_args.kwargs.get("proxy_url", "") == ""
