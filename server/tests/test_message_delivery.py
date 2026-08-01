from unittest.mock import patch

from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.mail.imap.message_store import save_messages
from hx_email.server.mail.verification import MailboxMessage
from hx_email.server.notifications import (
    retry_pending_deliveries,
)
from hx_email.server.notifications import (
    test_script_pipeline as run_script_pipeline_test,
)
from hx_email.server.notifications.impl.channels import send_delivery
from hx_email.server.notifications.models import StoredMessageEvent
from hx_email.server.settings_service import set_setting


def create_mail_target(
    settings: Settings,
    *,
    notify_enabled: bool = True,
    group_notify_enabled: bool | None = None,
) -> int:
    with connect(settings) as connection:
        group_id: int | None = None
        if group_notify_enabled is not None:
            group_id = int(
                connection.execute(
                    "INSERT INTO groups (user_id, name, notify_enabled) VALUES (1, 'group', ?)",
                    (1 if group_notify_enabled else 0,),
                ).lastrowid
            )
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
                " (user_id, email_account_id, address, notify_enabled, group_id)"
                " VALUES (1, ?, ?, ?, ?)",
                (account_id, "owner@example.com", 1 if notify_enabled else 0, group_id),
            ).lastrowid
        )
    return email_id


def new_message() -> MailboxMessage:
    return MailboxMessage(
        recipient_address="owner@example.com",
        from_address="sender@example.com",
        subject="Verification code",
        body="Your code is 482913",
        received_at="2026-08-01T10:00:00Z",
        message_id="201",
    )


def stored_event() -> StoredMessageEvent:
    return StoredMessageEvent(
        id=1,
        user_id=1,
        usable_email_id=1,
        email_account_id=1,
        address="owner@example.com",
        group_id=2,
        group_name="registrations",
        email_notify_enabled=True,
        group_notify_enabled=True,
        account_telegram_enabled=True,
        from_address="sender@example.com",
        recipient_address="owner@example.com",
        subject="Verification code",
        body="Your code is 482913",
        received_at="2026-08-01T10:00:00Z",
    )


def delivery_row(settings: Settings):
    with connect(settings) as connection:
        return connection.execute(
            "SELECT channel, status, attempts, last_error FROM message_deliveries"
        ).fetchone()


def test_new_message_dispatch_is_deduplicated(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    email_id = create_mail_target(settings)
    set_setting(settings, "webhook_notification_enabled", "true")
    set_setting(settings, "webhook_notification_url", "https://hooks.example.com/mail")

    with patch("hx_email.server.notifications.dispatch.send_delivery") as send_delivery:
        first = save_messages(settings, 1, email_id, 1, [new_message()])
        second = save_messages(settings, 1, email_id, 1, [new_message()])

    row = delivery_row(settings)
    assert first == 1
    assert second == 0
    assert send_delivery.call_count == 1
    assert dict(row)["status"] == "sent"


def test_failed_delivery_is_retried_and_then_marked_sent(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    email_id = create_mail_target(settings)
    set_setting(settings, "webhook_notification_enabled", "true")
    set_setting(settings, "webhook_notification_url", "https://hooks.example.com/mail")

    with patch(
        "hx_email.server.notifications.dispatch.send_delivery",
        side_effect=RuntimeError("callback down"),
    ):
        save_messages(settings, 1, email_id, 1, [new_message()])
    failed_row = dict(delivery_row(settings))
    assert failed_row["status"] == "failed"
    assert failed_row["attempts"] == 1

    with patch("hx_email.server.notifications.dispatch.send_delivery"):
        summary = retry_pending_deliveries(settings)

    sent_row = dict(delivery_row(settings))
    assert summary.sent == 1
    assert sent_row["status"] == "sent"
    assert sent_row["attempts"] == 2


def test_muted_email_does_not_create_delivery_jobs(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    email_id = create_mail_target(settings, notify_enabled=False)
    set_setting(settings, "webhook_notification_enabled", "true")
    set_setting(settings, "webhook_notification_url", "https://hooks.example.com/mail")

    save_messages(settings, 1, email_id, 1, [new_message()])

    assert delivery_row(settings) is None


def test_muted_group_does_not_create_delivery_jobs(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    email_id = create_mail_target(settings, group_notify_enabled=False)
    set_setting(settings, "webhook_notification_enabled", "true")
    set_setting(settings, "webhook_notification_url", "https://hooks.example.com/mail")

    save_messages(settings, 1, email_id, 1, [new_message()])

    assert delivery_row(settings) is None


def test_webhook_delivery_posts_structured_new_mail_event(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    set_setting(settings, "webhook_notification_url", "https://hooks.example.com/mail")
    set_setting(settings, "webhook_notification_token", "callback-secret")

    with patch(
        "hx_email.server.notifications.impl.channels._open_json_request",
        return_value=(202, "accepted"),
    ) as post_json:
        send_delivery(settings, stored_event(), "webhook")

    url, payload, headers = post_json.call_args.args
    assert url == "https://hooks.example.com/mail"
    assert headers == {"Authorization": "Bearer callback-secret"}
    assert payload["event"] == "new_mail"
    assert payload["usable_email"]["address"] == "owner@example.com"
    assert payload["message"]["verification_code"] == "482913"


def test_email_delivery_forwards_original_message_body(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    set_setting(settings, "email_notification_recipient", "archive@example.com")
    set_setting(settings, "email_notification_smtp_host", "smtp.example.com")
    set_setting(settings, "email_notification_smtp_user", "sender@example.com")
    set_setting(settings, "email_notification_smtp_password", "secret")

    with patch("hx_email.server.notifications.impl.channels.smtplib.SMTP") as smtp:
        send_delivery(settings, stored_event(), "email")

    client = smtp.return_value.__enter__.return_value
    forwarded = client.send_message.call_args.args[0]
    assert forwarded["To"] == "archive@example.com"
    assert forwarded["Subject"] == "Fwd: Verification code"
    assert "Your code is 482913" in forwarded.get_content()


def test_shell_pipeline_receives_json_on_stdin(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    script_path = tmp_path / "notify.sh"
    script_path.write_text("#!/bin/sh\nread payload\nprintf '%s' \"$payload\"\n", encoding="utf-8")

    result = run_script_pipeline_test(settings, str(script_path))

    assert result["success"] is True
    assert '"event": "test"' in str(result["message"])
