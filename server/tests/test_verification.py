from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate

API = "/api/v1"


class FakeMailboxProvider:
    def __init__(self, messages):
        self.messages = messages

    def read_messages(self, email_account):
        return self.messages


def login_admin(client: TestClient, settings: Settings) -> dict[str, str]:
    session = client.post(
        f"{API}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    ).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def test_verification_reading_filters_messages_by_target_usable_email_address(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    mailbox = FakeMailboxProvider(
        [
            {
                "recipient_address": "owner@example.com",
                "subject": "Owner verification",
                "body": "Your code is 381927. Confirm at https://service.test/owner",
            },
            {
                "recipient_address": "alias@example.com",
                "subject": "Alias verification",
                "body": "Your code is 482916. Confirm at https://service.test/alias",
            },
        ]
    )
    client = TestClient(create_app(settings, mailbox_provider=mailbox))
    headers = login_admin(client, settings)

    account = client.post(
        f"{API}/email-accounts",
        json={
            "provider": "imap",
            "primary_address": "owner@example.com",
            "display_name": "Owner",
            "alias_addresses": ["alias@example.com"],
        },
        headers=headers,
    ).json()

    primary_reading = client.post(
        f"{API}/usable-emails/{account['usable_emails'][0]['id']}/verification/read",
        headers=headers,
    )
    alias_reading = client.post(
        f"{API}/usable-emails/{account['usable_emails'][1]['id']}/verification/read",
        headers=headers,
    )

    assert primary_reading.status_code == 200
    assert primary_reading.json()["usable_email"]["address"] == "owner@example.com"
    assert primary_reading.json()["matches"] == [
        {
            "code": "381927",
            "link": None,
            "recipient_address": "owner@example.com",
            "certainty": "certain",
            "subject": "Owner verification",
        }
    ]
    assert alias_reading.status_code == 200
    assert alias_reading.json()["usable_email"]["address"] == "alias@example.com"
    assert alias_reading.json()["matches"] == [
        {
            "code": "482916",
            "link": None,
            "recipient_address": "alias@example.com",
            "certainty": "certain",
            "subject": "Alias verification",
        }
    ]


def test_verification_reading_marks_messages_without_recipient_as_uncertain(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    mailbox = FakeMailboxProvider(
        [
            {
                "subject": "Verification",
                "body": "Your code is 593714. Confirm at https://service.test/uncertain",
            }
        ]
    )
    client = TestClient(create_app(settings, mailbox_provider=mailbox))
    headers = login_admin(client, settings)

    account = client.post(
        f"{API}/email-accounts",
        json={
            "provider": "imap",
            "primary_address": "owner@example.com",
            "display_name": "Owner",
        },
        headers=headers,
    ).json()

    reading = client.post(
        f"{API}/usable-emails/{account['primary_usable_email']['id']}/verification/read",
        headers=headers,
    )

    assert reading.status_code == 200
    assert reading.json()["matches"] == [
        {
            "code": "593714",
            "link": None,
            "recipient_address": None,
            "certainty": "uncertain",
            "subject": "Verification",
        }
    ]


def test_verification_history_is_isolated_by_user_and_usable_email(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    mailbox = FakeMailboxProvider(
        [
            {
                "recipient_address": "shared@example.com",
                "subject": "Shared verification",
                "body": "Your code is 642938. Confirm at https://service.test/shared",
            },
            {
                "recipient_address": "alias@example.com",
                "subject": "Alias verification",
                "body": "Your code is 753149. Confirm at https://service.test/alias",
            },
        ]
    )
    client = TestClient(create_app(settings, mailbox_provider=mailbox))
    admin_headers = login_admin(client, settings)
    client.put(f"{API}/admin/settings/registration", json={"enabled": True}, headers=admin_headers)
    alice = client.post(
        f"{API}/auth/register", json={"username": "alice", "password": "alice-pass"}
    ).json()
    bob = client.post(
        f"{API}/auth/register", json={"username": "bob", "password": "bob-pass"}
    ).json()
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}

    alice_account = client.post(
        f"{API}/email-accounts",
        json={
            "provider": "imap",
            "primary_address": "shared@example.com",
            "display_name": "Alice",
            "alias_addresses": ["alias@example.com"],
        },
        headers=alice_headers,
    ).json()
    bob_account = client.post(
        f"{API}/email-accounts",
        json={
            "provider": "imap",
            "primary_address": "shared@example.com",
            "display_name": "Bob",
        },
        headers=bob_headers,
    ).json()

    client.post(
        f"{API}/usable-emails/{alice_account['primary_usable_email']['id']}/verification/read",
        headers=alice_headers,
    )
    client.post(
        f"{API}/usable-emails/{alice_account['usable_emails'][1]['id']}/verification/read",
        headers=alice_headers,
    )
    client.post(
        f"{API}/usable-emails/{bob_account['primary_usable_email']['id']}/verification/read",
        headers=bob_headers,
    )

    alice_primary_history = client.get(
        f"{API}/usable-emails/{alice_account['primary_usable_email']['id']}/verification/history",
        headers=alice_headers,
    )
    alice_alias_history = client.get(
        f"{API}/usable-emails/{alice_account['usable_emails'][1]['id']}/verification/history",
        headers=alice_headers,
    )
    bob_history = client.get(
        f"{API}/usable-emails/{bob_account['primary_usable_email']['id']}/verification/history",
        headers=bob_headers,
    )

    assert alice_primary_history.status_code == 200
    assert [match["code"] for match in alice_primary_history.json()["matches"]] == ["642938"]
    assert [match["code"] for match in alice_alias_history.json()["matches"]] == ["753149"]
    assert [match["code"] for match in bob_history.json()["matches"]] == ["642938"]


def test_plus_subaddress_compatibility_does_not_replace_real_alias_filtering(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    mailbox = FakeMailboxProvider(
        [
            {
                "recipient_address": "owner+tag@example.com",
                "subject": "Plus verification",
                "body": "Your code is 618264. Confirm at https://service.test/plus",
            },
            {
                "recipient_address": "alias@example.com",
                "subject": "Alias verification",
                "body": "Your code is 729315. Confirm at https://service.test/alias",
            },
        ]
    )
    client = TestClient(create_app(settings, mailbox_provider=mailbox))
    headers = login_admin(client, settings)

    account = client.post(
        f"{API}/email-accounts",
        json={
            "provider": "imap",
            "primary_address": "owner@example.com",
            "display_name": "Owner",
            "alias_addresses": ["alias@example.com"],
        },
        headers=headers,
    ).json()
    plus_email = client.post(
        f"{API}/usable-emails",
        json={"address": "owner+tag@example.com", "label": "Plus tag"},
        headers=headers,
    ).json()

    alias_reading = client.post(
        f"{API}/usable-emails/{account['usable_emails'][1]['id']}/verification/read",
        headers=headers,
    )
    plus_reading = client.post(
        f"{API}/usable-emails/{plus_email['id']}/verification/read",
        headers=headers,
    )

    direct_plus_reading = client.get(
        f"{API}/emails/owner+tag@example.com/extract-verification",
        headers=headers,
    )

    assert [match["code"] for match in alias_reading.json()["matches"]] == ["729315"]
    assert plus_reading.status_code == 200
    assert [match["code"] for match in plus_reading.json()["matches"]] == ["618264"]
    assert direct_plus_reading.status_code == 200
    assert direct_plus_reading.json()["verification_code"] == "618264"
