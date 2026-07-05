from __future__ import annotations

from unittest.mock import patch

from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.mail import EmailAccountMailbox
from hx_email.server.mail.imap.imap_helpers import parse_date
from hx_email.server.mail.imap.imap_provider import IMAPMailboxProvider


class FakeImapConnection:
    def __init__(self, host: str, port: int, **kwargs: object) -> None:
        _ = kwargs
        self.host: str = host
        self.port: int = port
        self.selected: list[str] = []
        self.fetch_ids: list[str] = []
        self.fetch_call_count: int = 0

    def authenticate(self, mechanism: str, authobject: object) -> None:
        _ = (mechanism, authobject)

    def login(self, username: str, password: str) -> None:
        _ = (username, password)

    def select(self, folder: str, readonly: bool = False) -> tuple[str, list[bytes]]:
        _ = readonly
        self.selected.append(folder)
        return "OK", [b"4"]

    def uid(self, command: str, *args: object) -> tuple[str, list[object]]:
        if command == "SEARCH":
            return "OK", [b"1 2 3 4"]
        if command == "FETCH":
            self.fetch_call_count += 1
            uid_set = args[0]
            uid_text = uid_set.decode("ascii") if isinstance(uid_set, bytes) else str(uid_set)
            response: list[tuple[bytes, bytes]] = []
            for uid in uid_text.split(","):
                self.fetch_ids.append(uid)
                subject = "Newest" if uid == "4" else "Third"
                response.append(
                    (f"{uid.encode()!r} (UID {uid} RFC822 {{1}}".encode(), raw_message(subject))
                )
            return "OK", response
        return "NO", []

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

    assert fake.selected == ["Junk Email"]
    assert fake.fetch_ids == ["4", "3"]
    assert fake.fetch_call_count == 1
    assert [message.subject for message in messages] == ["Newest", "Third"]


def test_imap_provider_fetches_only_uids_newer_than_since_uid(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    with connect(settings) as conn:
        conn.execute(
            """
            INSERT INTO email_accounts
                (id, user_id, provider, primary_address, imap_host, username, imap_password)
            VALUES (1, 1, 'gmail', 'owner@example.com', 'imap.gmail.com',
                    'owner@example.com', 'secret')
            """
        )

    fake = FakeImapConnection("imap.gmail.com", 993)

    with patch("hx_email.server.mail.imap.imap_provider.imaplib.IMAP4_SSL", return_value=fake):
        messages = IMAPMailboxProvider(settings).read_messages(
            EmailAccountMailbox(id=1, provider="gmail", primary_address="owner@example.com"),
            top=10,
            since_uid="3",
        )

    assert fake.fetch_ids == ["4"]
    assert fake.fetch_call_count == 1
    assert [message.subject for message in messages] == ["Newest"]


def test_parse_date_converts_imap_timestamp_to_local_timezone() -> None:
    assert parse_date("Fri, 04 Jul 2026 08:00:00 +0000") == "2026-07-04 16:00:00"
    assert parse_date("Fri, 04 Jul 2026 01:00:00 -0700") == "2026-07-04 16:00:00"


def test_imap_provider_uses_group_proxy_for_account_group(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    with connect(settings) as conn:
        conn.execute(
            """
            INSERT INTO groups (id, user_id, name, color, proxy_url)
            VALUES (10, 1, 'Proxy', '#58a6ff', 'http://127.0.0.1:2334')
            """
        )
        conn.execute(
            """
            INSERT INTO email_accounts
                (id, user_id, provider, primary_address, imap_host, client_id,
                 refresh_token, group_id)
            VALUES (1, 1, 'outlook', 'owner@example.com', 'outlook.live.com', 'cid',
                    'rt', 10)
            """
        )

    fake = FakeImapConnection("outlook.live.com", 993)
    proxy_calls: list[tuple[str, str, int, int]] = []

    def fake_proxy(proxy_url: str, host: str, port: int, timeout: int = 30) -> FakeImapConnection:
        proxy_calls.append((proxy_url, host, port, timeout))
        return fake

    with (
        patch(
            "hx_email.server.mail.imap.imap_provider.try_get_imap_token",
            return_value=("token", "consumers"),
        ),
        patch("hx_email.server.mail.imap.imap_provider.imap_connect_via_proxy", fake_proxy),
        patch("hx_email.server.mail.imap.imap_provider.imaplib.IMAP4_SSL") as direct_connect,
    ):
        messages = IMAPMailboxProvider(settings).read_messages(
            EmailAccountMailbox(id=1, provider="outlook", primary_address="owner@example.com"),
            top=1,
        )

    assert proxy_calls[0][:3] == ("http://127.0.0.1:2334", "outlook.live.com", 993)
    direct_connect.assert_not_called()
    assert [message.subject for message in messages] == ["Newest"]
