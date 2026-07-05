from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.mail.imap.message_store import legacy_body_hash
from hx_email.server.mail.verification import MailboxMessage
from test_account_mail_fetch import API, SequenceMailboxProvider, create_account, login_admin


def test_fetch_emails_uses_cached_latest_uid_for_next_fetch(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    provider = SequenceMailboxProvider(
        [
            [
                MailboxMessage(
                    recipient_address="owner@example.com",
                    subject="First Gmail message",
                    body="Your code is 100100",
                    from_address="security@example.com",
                    received_at="2026-07-04 10:00:00",
                    message_id="100",
                )
            ],
            [
                MailboxMessage(
                    recipient_address="owner@example.com",
                    subject="Second Gmail message",
                    body="Your code is 200200",
                    from_address="security@example.com",
                    received_at="2026-07-04 10:01:00",
                    message_id="101",
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
    assert provider.since_uids == ["", "100"]
    assert [message["subject"] for message in messages.json()["messages"]] == [
        "Second Gmail message",
        "First Gmail message",
    ]


def test_fetch_emails_backfills_uid_for_existing_cached_message(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    provider = SequenceMailboxProvider(
        [
            [
                MailboxMessage(
                    recipient_address="owner@example.com",
                    subject="Migrated cached message",
                    body="Your code is 300300",
                    from_address="security@example.com",
                    received_at="2026-07-04 10:00:00",
                    message_id="100",
                )
            ],
            [
                MailboxMessage(
                    recipient_address="owner@example.com",
                    subject="Message after migrated cache",
                    body="Your code is 400400",
                    from_address="security@example.com",
                    received_at="2026-07-04 10:02:00",
                    message_id="101",
                )
            ],
        ]
    )
    client = TestClient(create_app(settings, mailbox_provider=provider))
    headers = login_admin(client, settings)
    account = create_account(client, headers)
    primary_id = account["primary_usable_email"]["id"]
    with connect(settings) as conn:
        conn.execute(
            """
            INSERT INTO fetched_messages (
                user_id, usable_email_id, email_account_id, from_address,
                recipient_address, subject, body, received_at, body_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                primary_id,
                account["id"],
                "security@example.com",
                "owner@example.com",
                "Migrated cached message",
                "Your code is 300300",
                "2026-07-04 10:00:00",
                legacy_body_hash("Your code is 300300"),
            ),
        )

    first_fetch = client.post(f"{API}/usable-emails/{primary_id}/fetch-emails", headers=headers)
    second_fetch = client.post(f"{API}/usable-emails/{primary_id}/fetch-emails", headers=headers)

    assert first_fetch.json()["messages_stored"] == 0
    assert second_fetch.json()["messages_stored"] == 1
    assert provider.since_uids == ["", "100"]
