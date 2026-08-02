from pathlib import Path
from unittest.mock import patch

from hx_email.config import Settings
from hx_email.server.external_api.impl.mail.mail_service import get_latest_message
from hx_email.server.mail import EmailAccountMailbox, MailboxMessage


class NewestFirstMailboxProvider:
    def __init__(self, messages: list[MailboxMessage]) -> None:
        self.messages: list[MailboxMessage] = messages

    def read_messages(self, email_account: EmailAccountMailbox) -> list[MailboxMessage]:
        _ = email_account
        return self.messages


def test_latest_message_uses_first_message_from_newest_first_provider(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    account = EmailAccountMailbox(
        id=1,
        provider="imap",
        primary_address="owner@example.com",
    )
    provider = NewestFirstMailboxProvider(
        [
            MailboxMessage(
                recipient_address="owner@example.com",
                subject="Newest verification code",
                body="Your code is 769328",
                received_at="2026-08-02 10:02:00",
                message_id="newest",
            ),
            MailboxMessage(
                recipient_address="owner@example.com",
                subject="Older verification code",
                body="Your code is 137529",
                received_at="2026-08-02 10:01:00",
                message_id="older",
            ),
        ]
    )

    with patch(
        "hx_email.server.external_api.impl.mail.mail_service._find_email_account",
        return_value=account,
    ):
        result: dict[str, object] = get_latest_message(
            settings,
            provider,
            "owner@example.com",
        )

    message = result["message"]
    assert isinstance(message, dict)
    assert result["found"] is True
    assert message["id"] == "1"
    assert message["subject"] == "Newest verification code"
