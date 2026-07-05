from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.mail.verification import MailboxMessage

API = "/api/v1"


class SequenceMailboxProvider:
    def __init__(self, batches):
        self.batches = list(batches)
        self.calls = 0
        self.last_top = 0
        self.since_uids = []

    def read_messages(self, email_account, folder="inbox", skip=0, top=50, since_uid=""):
        _ = (email_account, folder, skip)
        self.last_top = top
        self.since_uids.append(since_uid)
        self.calls += 1
        if self.calls <= len(self.batches):
            return self.batches[self.calls - 1]
        return self.batches[-1] if self.batches else []


def login_admin(client: TestClient, settings: Settings) -> dict[str, str]:
    session = client.post(
        f"{API}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    ).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def create_account(client: TestClient, headers: dict[str, str]) -> dict:
    return client.post(
        f"{API}/email-accounts",
        json={
            "provider": "imap",
            "primary_address": "owner@example.com",
            "display_name": "Owner",
            "imap_host": "imap.example.com",
            "imap_password": "secret",
            "alias_addresses": ["alias@example.com"],
        },
        headers=headers,
    ).json()


def test_fetch_emails_uses_injected_provider_stores_cache_and_updates_refresh_time(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    provider = SequenceMailboxProvider(
        [
            [
                MailboxMessage(
                    recipient_address="owner@example.com",
                    subject="Owner code",
                    body="Your code is 111111",
                    from_address="service@example.com",
                    received_at="2026-06-25 10:00:00",
                ),
                MailboxMessage(
                    recipient_address="alias@example.com",
                    subject="Alias code",
                    body="Your code is 222222",
                    from_address="service@example.com",
                    received_at="2026-06-25 10:01:00",
                ),
            ]
        ]
    )
    client = TestClient(create_app(settings, mailbox_provider=provider))
    headers = login_admin(client, settings)
    account = create_account(client, headers)
    primary_id = account["usable_emails"][0]["id"]
    alias_id = account["usable_emails"][1]["id"]

    before = client.get(f"{API}/usable-emails/{primary_id}/messages", headers=headers)
    fetched = client.post(f"{API}/usable-emails/{primary_id}/fetch-emails", headers=headers)
    primary_after = client.get(f"{API}/usable-emails/{primary_id}/messages", headers=headers)
    alias_after = client.get(f"{API}/usable-emails/{alias_id}/messages", headers=headers)
    accounts_after = client.get(f"{API}/email-accounts", headers=headers)

    assert before.status_code == 200
    assert before.json()["messages"] == []
    assert fetched.status_code == 200
    assert fetched.json()["messages_stored"] == 2
    assert fetched.json()["error"] == ""
    assert provider.calls == 1
    assert [m["subject"] for m in primary_after.json()["messages"]] == ["Owner code"]
    assert [m["subject"] for m in alias_after.json()["messages"]] == ["Alias code"]
    assert accounts_after.json()["accounts"][0]["last_refresh_at"]


def test_read_verification_fetches_latest_before_extracting_from_cached_messages(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    provider = SequenceMailboxProvider(
        [
            [
                MailboxMessage(
                    recipient_address="owner@example.com",
                    subject="Old verification",
                    body="Your code is 314159",
                    received_at="2026-06-25 10:00:00",
                )
            ],
            [
                MailboxMessage(
                    recipient_address="owner@example.com",
                    subject="New verification",
                    body="Your code is 271828",
                    received_at="2026-06-25 10:01:00",
                )
            ],
        ]
    )
    client = TestClient(create_app(settings, mailbox_provider=provider))
    headers = login_admin(client, settings)
    account = create_account(client, headers)
    primary_id = account["primary_usable_email"]["id"]

    fetched = client.post(f"{API}/usable-emails/{primary_id}/fetch-emails", headers=headers)
    reading = client.post(f"{API}/usable-emails/{primary_id}/verification/read", headers=headers)

    assert fetched.status_code == 200
    assert fetched.json()["messages_stored"] == 1
    assert [m["code"] for m in reading.json()["matches"]] == ["271828", "314159"]
    assert provider.calls == 2


def test_fetch_emails_stores_newer_message_with_same_body_and_subject(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    provider = SequenceMailboxProvider(
        [
            [
                MailboxMessage(
                    recipient_address="owner@example.com",
                    subject="Login notice",
                    body="Your account was used to sign in.",
                    from_address="security@example.com",
                    received_at="2026-06-25 10:00:00",
                    message_id="101",
                )
            ],
            [
                MailboxMessage(
                    recipient_address="owner@example.com",
                    subject="Login notice",
                    body="Your account was used to sign in.",
                    from_address="security@example.com",
                    received_at="2026-06-25 10:05:00",
                    message_id="102",
                )
            ],
        ]
    )
    client = TestClient(create_app(settings, mailbox_provider=provider))
    headers = login_admin(client, settings)
    account = create_account(client, headers)
    primary_id = account["primary_usable_email"]["id"]

    first_fetch = client.post(f"{API}/usable-emails/{primary_id}/fetch-emails", headers=headers)
    second_fetch = client.post(f"{API}/usable-emails/{primary_id}/fetch-emails", headers=headers)
    messages = client.get(f"{API}/usable-emails/{primary_id}/messages", headers=headers)

    assert first_fetch.json()["messages_stored"] == 1
    assert second_fetch.json()["messages_stored"] == 1
    assert [message["received_at"] for message in messages.json()["messages"]] == [
        "2026-06-25 10:05:00",
        "2026-06-25 10:00:00",
    ]
    assert provider.last_top >= 200


def test_fetch_emails_for_standalone_plus_email_uses_base_account(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    provider = SequenceMailboxProvider(
        [
            [
                MailboxMessage(
                    recipient_address="GitHub <owner+github@example.com>",
                    subject="GitHub verification",
                    body="Your code is 123456",
                    from_address="noreply@github.com",
                    received_at="2026-06-25 10:08:00",
                    message_id="github-1",
                )
            ]
        ]
    )
    client = TestClient(create_app(settings, mailbox_provider=provider))
    headers = login_admin(client, settings)
    account = create_account(client, headers)
    plus_email = client.post(
        f"{API}/usable-emails",
        json={"address": "owner+github@example.com", "label": "GitHub"},
        headers=headers,
    ).json()

    listed = client.get(f"{API}/usable-emails", headers=headers)
    fetched = client.post(f"{API}/usable-emails/{plus_email['id']}/fetch-emails", headers=headers)
    plus_messages = client.get(f"{API}/usable-emails/{plus_email['id']}/messages", headers=headers)

    listed_plus = next(
        item for item in listed.json()["usable_emails"] if item["id"] == plus_email["id"]
    )
    assert listed_plus["email_account_id"] == account["id"]
    assert fetched.status_code == 200
    assert fetched.json()["error"] == ""
    assert [message["subject"] for message in plus_messages.json()["messages"]] == [
        "GitHub verification"
    ]


def test_read_verification_reuses_recent_code_then_waits_for_new_code_after_cooldown(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    provider = SequenceMailboxProvider(
        [
            [
                MailboxMessage(
                    recipient_address="owner@example.com",
                    subject="Old verification",
                    body="Your code is 314159",
                    received_at="2026-06-25 10:00:00",
                )
            ],
            [
                MailboxMessage(
                    recipient_address="owner@example.com",
                    subject="Old verification",
                    body="Your code is 314159",
                    received_at="2026-06-25 10:00:00",
                )
            ],
            [
                MailboxMessage(
                    recipient_address="owner@example.com",
                    subject="New verification",
                    body="Your code is 271828",
                    received_at="2026-06-25 10:01:00",
                ),
                MailboxMessage(
                    recipient_address="owner@example.com",
                    subject="Old verification",
                    body="Your code is 314159",
                    received_at="2026-06-25 10:00:00",
                ),
            ],
        ]
    )
    client = TestClient(create_app(settings, mailbox_provider=provider))
    headers = login_admin(client, settings)
    account = create_account(client, headers)
    primary_id = account["primary_usable_email"]["id"]

    first = client.post(f"{API}/usable-emails/{primary_id}/verification/read", headers=headers)
    second = client.post(f"{API}/usable-emails/{primary_id}/verification/read", headers=headers)
    with connect(settings) as conn:
        old_started_at = (datetime.now(UTC) - timedelta(seconds=31)).isoformat()
        conn.execute(
            """
            UPDATE verification_readings
            SET created_at = ?
            WHERE usable_email_id = ? AND code = '314159'
            """,
            (old_started_at, primary_id),
        )
    third = client.post(f"{API}/usable-emails/{primary_id}/verification/read", headers=headers)

    assert [m["code"] for m in first.json()["matches"]] == ["314159"]
    assert [m["code"] for m in second.json()["matches"]] == ["314159"]
    assert [m["code"] for m in third.json()["matches"]] == ["271828", "314159"]
    assert provider.calls == 3
