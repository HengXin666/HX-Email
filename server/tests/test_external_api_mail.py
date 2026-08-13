from pathlib import Path
from unittest.mock import patch

from hx_email.config import Settings
from hx_email.server.external_api.impl.mail.mail_service import (
    get_latest_message,
    get_message_detail,
    get_messages,
)
from hx_email.server.external_api.impl.mail.verification_service import (
    extract_verification_code,
)
from hx_email.server.mail import EmailAccountMailbox, MailboxMessage
from hx_email.server.mail.temp_mail import ProviderMailbox, TempMailMessage


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


# ========== 临时邮箱 (usable_emails.kind='temp') 外部 API 读取 ==========


class FakeTempMailProvider:
    """Minimal TempMailProvider returning fixed messages."""

    def __init__(self, messages: list[TempMailMessage]) -> None:
        self.messages: list[TempMailMessage] = messages

    def create_mailbox(self, requested_address: str | None = None) -> ProviderMailbox:
        _ = requested_address
        return ProviderMailbox(provider_mailbox_id="mailbox-1", address="temp-1@example.com")

    def list_messages(self, provider_mailbox_id: str) -> list[TempMailMessage]:
        _ = provider_mailbox_id
        return self.messages


def _seed_temp_mailbox(
    settings: Settings,
    provider: FakeTempMailProvider,
    address: str = "temp-1@example.com",
) -> None:
    from hx_email.database import migrate
    from hx_email.server.mail.temp_mail import create_cf_temp_mailbox

    migrate(settings)
    create_cf_temp_mailbox(settings, 1, provider, address=address, label="tmp")


def test_external_verification_code_reads_temp_mail(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    provider = FakeTempMailProvider(
        [
            TempMailMessage(
                id="cf_1",
                from_address="noreply@openai.com",
                subject="Your OpenAI verification code",
                text="Your verification code is 884213",
                received_at="2026-08-13 10:00:00",
            ),
        ]
    )
    _seed_temp_mailbox(settings, provider)

    result = extract_verification_code(
        settings,
        NewestFirstMailboxProvider([]),
        "temp-1@example.com",
        temp_mail_providers={"cf": provider},
    )

    assert result["verification_code"] == "884213"
    assert result["match_count"] == 1


def test_external_verification_code_extracts_html_only_temp_mail(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    provider = FakeTempMailProvider(
        [
            TempMailMessage(
                id="cf_2",
                from_address="account-security@microsoft.com",
                subject="Microsoft account security code",
                text="",
                html=(
                    "<html><body><p>Your Microsoft security code is "
                    "<b>771920</b>.</p></body></html>"
                ),
                received_at="2026-08-13 10:01:00",
            ),
        ]
    )
    _seed_temp_mailbox(settings, provider)

    result = extract_verification_code(
        settings,
        NewestFirstMailboxProvider([]),
        "temp-1@example.com",
        temp_mail_providers={"cf": provider},
    )

    assert result["verification_code"] == "771920"


def test_external_messages_list_reads_temp_mail(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    provider = FakeTempMailProvider(
        [
            TempMailMessage(
                id="cf_1",
                from_address="noreply@example.com",
                subject="Welcome",
                text="Welcome to the service",
                received_at="2026-08-13 10:00:00",
            ),
        ]
    )
    _seed_temp_mailbox(settings, provider)

    result = get_messages(
        settings,
        NewestFirstMailboxProvider([]),
        "temp-1@example.com",
        temp_mail_providers={"cf": provider},
    )

    assert result["total"] == 1
    messages = result["messages"]
    assert isinstance(messages, list)
    assert messages[0]["subject"] == "Welcome"


def test_external_message_detail_reads_temp_mail(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    provider = FakeTempMailProvider(
        [
            TempMailMessage(
                id="cf_42",
                from_address="noreply@example.com",
                subject="Reset link",
                text="Click https://example.com/reset?t=abc123 to reset",
                received_at="2026-08-13 10:00:00",
            ),
        ]
    )
    _seed_temp_mailbox(settings, provider)

    result = get_message_detail(
        settings,
        NewestFirstMailboxProvider([]),
        "temp-1@example.com",
        "cf_42",
        temp_mail_providers={"cf": provider},
    )

    assert result["found"] is True
    message = result["message"]
    assert isinstance(message, dict)
    assert "example.com/reset" in message["body"]
