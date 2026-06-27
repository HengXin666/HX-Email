from __future__ import annotations

from unittest.mock import patch

from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.mail import EmailAccountMailbox
from hx_email.server.mail.imap.imap_provider import IMAPMailboxProvider


class FakeImapConnection:
    def __init__(self, host: str, port: int, **kwargs: object) -> None:
        _ = kwargs
        self.host: str = host
        self.port: int = port
        self.selected: list[str] = []
        self.fetch_ids: str = ""

    def authenticate(self, mechanism: str, authobject: object) -> None:
        _ = (mechanism, authobject)

    def select(self, folder: str, readonly: bool = False) -> tuple[str, list[bytes]]:
        _ = readonly
        self.selected.append(folder)
        return "OK", [b"4"]

    def search(self, charset: object, criterion: str) -> tuple[str, list[object]]:
        _ = (charset, criterion)
        return "OK", [b"1 2 3 4"]

    def fetch(self, ids: str, query: str) -> tuple[str, list[object]]:
        _ = query
        self.fetch_ids = ids
        return "OK", [
            (b"4 (RFC822 {1}", raw_message("Newest")),
            (b"3 (RFC822 {1}", raw_message("Third")),
        ]

    def close(self) -> None:
        pass

    def logout(self) -> None:
        pass


def raw_message(subject: str) -> bytes:
    return (
        f"Subject: {subject}\r\n"
        "From: service@example.com\r\n"
        "To: owner@example.com\r\n"
        "Date: Thu, 25 Jun 2026 10:00:00 +0000\r\n"
        "\r\n"
        "Body"
    ).encode()


def test_imap_provider_fetches_latest_message_ids_first_like_reference_project(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    with connect(settings) as conn:
        conn.execute(
            """
            INSERT INTO email_accounts
                (id, user_id, provider, primary_address, imap_host, client_id, refresh_token)
            VALUES (1, 1, 'outlook', 'owner@example.com', 'outlook.live.com', 'cid', 'rt')
            """
        )

    fake = FakeImapConnection("outlook.live.com", 993)

    with (
        patch(
            "hx_email.server.mail.imap.imap_provider.try_get_imap_token",
            return_value=("token", "consumers"),
        ),
        patch("hx_email.server.mail.imap.imap_provider.imaplib.IMAP4_SSL", return_value=fake),
    ):
        messages = IMAPMailboxProvider(settings).read_messages_folder(
            EmailAccountMailbox(id=1, provider="outlook", primary_address="owner@example.com"),
            folder="junkemail",
            top=2,
        )

    assert fake.selected == ["Junk"]
    assert fake.fetch_ids == "4,3"
    assert [message.subject for message in messages] == ["Newest", "Third"]
