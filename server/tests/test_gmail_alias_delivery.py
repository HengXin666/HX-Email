from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate
from hx_email.server.mail.verification import MailboxMessage

API = "/api/v1"


class FolderMailboxProvider:
    def __init__(self, messages: list[MailboxMessage]) -> None:
        self.messages = messages
        self.folders: list[str] = []

    def read_messages(
        self,
        email_account,
        folder: str = "inbox",
        skip: int = 0,
        top: int = 50,
    ) -> list[MailboxMessage]:
        _ = (email_account, folder, skip, top)
        return self.messages

    def read_messages_folder(
        self,
        email_account,
        *,
        folder: str,
        top: int,
        skip: int = 0,
    ) -> list[MailboxMessage]:
        _ = (email_account, top, skip)
        self.folders.append(folder)
        return self.messages if folder == "inbox" else []


def login_admin(client: TestClient, settings: Settings) -> dict[str, str]:
    session = client.post(
        f"{API}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    ).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def create_gmail_account(client: TestClient, headers: dict[str, str]) -> dict[str, object]:
    return client.post(
        f"{API}/email-accounts",
        json={
            "provider": "gmail",
            "primary_address": "llh282000500@gmail.com",
            "display_name": "Gmail",
            "imap_host": "imap.gmail.com",
            "imap_password": "secret",
        },
        headers=headers,
    ).json()


def test_gmail_dot_alias_message_is_saved_for_base_account(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    provider = FolderMailboxProvider(
        [
            MailboxMessage(
                recipient_address="Service <llh.282.000500@gmail.com>",
                subject="Gmail dot alias",
                body="Your code is 123456",
                from_address="service@example.com",
                received_at="2026-07-04 09:00:00",
                message_id="gmail-dot-1",
            )
        ]
    )
    client = TestClient(create_app(settings, mailbox_provider=provider))
    headers = login_admin(client, settings)
    account = create_gmail_account(client, headers)
    primary_id = account["primary_usable_email"]["id"]

    fetched = client.post(f"{API}/usable-emails/{primary_id}/fetch-emails", headers=headers)
    messages = client.get(f"{API}/usable-emails/{primary_id}/messages", headers=headers)

    assert fetched.json()["error"] == ""
    assert fetched.json()["messages_stored"] == 1
    assert [message["subject"] for message in messages.json()["messages"]] == ["Gmail dot alias"]


def test_inbox_message_with_unregistered_recipient_is_not_dropped(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    provider = FolderMailboxProvider(
        [
            MailboxMessage(
                recipient_address="forwarded-or-bcc@example.net",
                subject="Delivered inbox message",
                body="This message reached the account inbox.",
                from_address="service@example.com",
                received_at="2026-07-04 09:05:00",
                message_id="inbox-unmatched-1",
            )
        ]
    )
    client = TestClient(create_app(settings, mailbox_provider=provider))
    headers = login_admin(client, settings)
    account = create_gmail_account(client, headers)
    primary_id = account["primary_usable_email"]["id"]

    fetched = client.post(f"{API}/usable-emails/{primary_id}/fetch-emails", headers=headers)
    messages = client.get(f"{API}/usable-emails/{primary_id}/messages", headers=headers)

    assert fetched.json()["messages_stored"] == 1
    assert [message["subject"] for message in messages.json()["messages"]] == [
        "Delivered inbox message"
    ]


def test_refresh_fetches_inbox_only_not_junk(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    provider = FolderMailboxProvider([])
    client = TestClient(create_app(settings, mailbox_provider=provider))
    headers = login_admin(client, settings)
    account = create_gmail_account(client, headers)
    primary_id = account["primary_usable_email"]["id"]

    client.post(f"{API}/usable-emails/{primary_id}/fetch-emails", headers=headers)

    assert provider.folders == ["inbox"]
