from __future__ import annotations

from email.utils import parsedate_to_datetime
from unittest.mock import patch

from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.security import decrypt_secret
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
        self.auth_mechanism: str = ""

    def authenticate(self, mechanism: str, authobject: object) -> None:
        _ = authobject
        self.auth_mechanism = mechanism

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
            return_value=("token", "consumers", ""),
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


def test_gmail_oauth_credentials_use_google_token_endpoint(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    with connect(settings) as conn:
        conn.execute(
            """
            INSERT INTO email_accounts
                (id, user_id, provider, primary_address, imap_host, client_id, refresh_token)
            VALUES (1, 1, 'gmail', 'owner@gmail.com', 'imap.gmail.com', 'google-cid', 'google-rt')
            """
        )
    fake = FakeImapConnection("imap.gmail.com", 993)

    with (
        patch(
            "hx_email.server.mail.imap.imap_provider.get_google_access_token",
            return_value="google-access-token",
        ) as google_token,
        patch("hx_email.server.mail.imap.imap_provider.try_get_imap_token") as microsoft_token,
        patch("hx_email.server.mail.imap.imap_provider.imaplib.IMAP4_SSL", return_value=fake),
    ):
        IMAPMailboxProvider(settings).read_messages(
            EmailAccountMailbox(id=1, provider="gmail", primary_address="owner@gmail.com"), top=1
        )

    google_token.assert_called_once()
    microsoft_token.assert_not_called()
    assert fake.auth_mechanism == "XOAUTH2"


def test_outlook_imap_persists_rotated_refresh_token(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    with connect(settings) as conn:
        conn.execute(
            """
            INSERT INTO email_accounts
                (id, user_id, provider, primary_address, client_id, refresh_token)
            VALUES (1, 1, 'outlook', 'owner@outlook.com', 'client-id', 'old-refresh-token')
            """
        )
    provider = IMAPMailboxProvider(settings)

    with (
        patch(
            "hx_email.server.mail.imap.imap_provider.try_get_imap_token",
            return_value=("access-token", "consumers", "rotated-refresh-token"),
        ),
        patch.object(provider, "_imap_fetch", return_value=[]),
    ):
        provider.read_messages(
            EmailAccountMailbox(id=1, provider="outlook", primary_address="owner@outlook.com")
        )

    with connect(settings) as connection:
        stored: str = str(
            connection.execute("SELECT refresh_token FROM email_accounts WHERE id = 1").fetchone()[
                "refresh_token"
            ]
        )
    assert decrypt_secret(settings, stored) == "rotated-refresh-token"


def test_gmail_oauth_uses_primary_address_instead_of_stale_imap_username(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    with connect(settings) as conn:
        conn.execute(
            """
            INSERT INTO email_accounts
                (id, user_id, provider, primary_address, username, client_id, refresh_token)
            VALUES (1, 1, 'gmail', 'correct@gmail.com', 'misspelled@gmail.com',
                    'google-cid', 'google-rt')
            """
        )

    provider = IMAPMailboxProvider(settings)
    with (
        patch(
            "hx_email.server.mail.imap.imap_provider.get_google_access_token",
            return_value="google-access-token",
        ),
        patch.object(provider, "_imap_fetch", return_value=[]) as imap_fetch,
    ):
        provider.read_messages(
            EmailAccountMailbox(id=1, provider="gmail", primary_address="correct@gmail.com")
        )

    assert imap_fetch.call_args.args[2] == "correct@gmail.com"
    assert imap_fetch.call_args.kwargs["use_xoauth2"] is True


def test_parse_date_converts_imap_timestamp_to_local_timezone() -> None:
    utc_value: str = "Fri, 04 Jul 2026 08:00:00 +0000"
    pacific_value: str = "Fri, 04 Jul 2026 01:00:00 -0700"
    expected_local: str = (
        parsedate_to_datetime(utc_value).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    )

    assert parse_date(utc_value) == expected_local
    assert parse_date(pacific_value) == expected_local


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
            return_value=("token", "consumers", ""),
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
