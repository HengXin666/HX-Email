from pathlib import Path
from unittest.mock import patch

from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.mail.imap.message_store import save_messages
from hx_email.server.mail.verification import MailboxMessage
from hx_email.server.settings_service import set_setting


def create_monitored_mailbox(settings: Settings) -> int:
    with connect(settings) as connection:
        account_id: int = int(
            connection.execute(
                "INSERT INTO email_accounts"
                " (user_id, provider, primary_address, imap_password)"
                " VALUES (1, 'imap', 'owner@example.com', 'password')"
            ).lastrowid
        )
        email_id: int = int(
            connection.execute(
                "INSERT INTO usable_emails"
                " (user_id, email_account_id, address)"
                " VALUES (1, ?, 'owner@example.com')",
                (account_id,),
            ).lastrowid
        )
    return email_id


def test_email_forwarding_skips_monitored_recipient(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    email_id: int = create_monitored_mailbox(settings)
    set_setting(settings, "email_notification_enabled", "true")
    set_setting(settings, "email_notification_recipient", "Owner@Example.com")
    set_setting(settings, "email_notification_smtp_host", "smtp.example.com")
    set_setting(settings, "email_notification_smtp_user", "sender@example.com")
    set_setting(settings, "email_notification_smtp_password", "secret")

    message = MailboxMessage(
        recipient_address="owner@example.com",
        from_address="sender@example.com",
        subject="Verification code",
        body="Your code is 482913",
        received_at="2026-08-01T10:00:00Z",
        message_id="loop-1",
    )
    with patch("hx_email.server.mail.impl.sending.providers.smtplib.SMTP") as smtp:
        save_messages(settings, 1, email_id, 1, [message])

    smtp.assert_not_called()
    with connect(settings) as connection:
        row = connection.execute("SELECT status, last_error FROM message_deliveries").fetchone()
    assert row is not None
    assert row["status"] == "skipped"
    assert "monitored mailbox" in row["last_error"]
