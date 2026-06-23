from dataclasses import dataclass

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate


@dataclass(frozen=True)
class FakeProviderMessage:
    id: str
    from_address: str
    subject: str
    text: str
    html: str = ""


class FakeCfTempMailProvider:
    def create_mailbox(self, requested_address: str | None = None) -> dict[str, str]:
        return {
            "provider_mailbox_id": requested_address or "issued@example.test",
            "address": requested_address or "issued@example.test",
        }

    def list_messages(self, provider_mailbox_id: str) -> list[FakeProviderMessage]:
        return []


class FakeMailboxProvider:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    def read_messages(self, email_account: object) -> list[dict[str, object]]:
        return self.messages


def login_admin(client: TestClient) -> dict[str, str]:
    session = client.post("/auth/login", json={"username": "admin", "password": "admin"}).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def test_mail_pool_claims_primary_alias_and_temp_usable_emails_independently(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    mailbox_provider = FakeMailboxProvider()
    client = TestClient(
        create_app(
            settings,
            mailbox_provider=mailbox_provider,
            temp_mail_providers={"cf": FakeCfTempMailProvider()},
        )
    )
    headers = login_admin(client)
    account = client.post(
        "/email-accounts",
        json={
            "provider": "imap",
            "primary_address": "owner@example.com",
            "display_name": "Owner",
            "alias_addresses": ["alias@example.com"],
        },
        headers=headers,
    ).json()
    temp = client.post(
        "/temp-mail/cf/mailboxes",
        json={"address": "temp@example.com", "label": "Temp"},
        headers=headers,
    ).json()

    for usable_email in [*account["usable_emails"], temp]:
        added = client.post(
            "/mail-pool/entries",
            json={"usable_email_id": usable_email["id"]},
            headers=headers,
        )
        assert added.status_code == 201

    first_claim = client.post(
        "/mail-pool/claim",
        json={"project_key": "github", "claim_key": "task-1"},
        headers=headers,
    ).json()
    second_claim = client.post(
        "/mail-pool/claim",
        json={"project_key": "github", "claim_key": "task-2"},
        headers=headers,
    ).json()
    third_claim = client.post(
        "/mail-pool/claim",
        json={"project_key": "github", "claim_key": "task-3"},
        headers=headers,
    ).json()

    assert [claim["status"] for claim in [first_claim, second_claim, third_claim]] == [
        "claimed",
        "claimed",
        "claimed",
    ]
    assert {first_claim["usable_email"]["address"], second_claim["usable_email"]["address"]} == {
        "owner@example.com",
        "alias@example.com",
    }
    assert third_claim["usable_email"]["address"] == "temp@example.com"

    mailbox_provider.messages = [
        {
            "recipient_address": second_claim["usable_email"]["address"],
            "subject": "Alias code",
            "body": "Your code is 135790",
        }
    ]
    reading = client.post(
        f"/usable-emails/{second_claim['usable_email']['id']}/verification/read",
        headers=headers,
    )
    assert (
        reading.json()["matches"][0]["recipient_address"] == second_claim["usable_email"]["address"]
    )


def test_mail_pool_release_complete_cooldown_project_reuse_and_user_isolation(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    admin_headers = login_admin(client)
    client.put("/admin/settings/registration", json={"enabled": True}, headers=admin_headers)
    alice = client.post(
        "/auth/register", json={"username": "alice", "password": "alice-pass"}
    ).json()
    bob = client.post("/auth/register", json={"username": "bob", "password": "bob-pass"}).json()
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}
    alice_email = client.post(
        "/usable-emails",
        json={"address": "shared@example.com", "label": "Alice"},
        headers=alice_headers,
    ).json()
    bob_email = client.post(
        "/usable-emails",
        json={"address": "shared@example.com", "label": "Bob"},
        headers=bob_headers,
    ).json()

    client.post(
        "/mail-pool/entries",
        json={"usable_email_id": alice_email["id"]},
        headers=alice_headers,
    )
    client.post(
        "/mail-pool/entries",
        json={"usable_email_id": bob_email["id"]},
        headers=bob_headers,
    )
    alice_claim = client.post(
        "/mail-pool/claim",
        json={"project_key": "github", "claim_key": "alice-task"},
        headers=alice_headers,
    ).json()
    bob_claim = client.post(
        "/mail-pool/claim",
        json={"project_key": "github", "claim_key": "bob-task"},
        headers=bob_headers,
    ).json()

    released = client.post(
        f"/mail-pool/entries/{alice_claim['usable_email']['id']}/release",
        headers=alice_headers,
    )
    reclaimed = client.post(
        "/mail-pool/claim",
        json={"project_key": "github", "claim_key": "alice-task-2"},
        headers=alice_headers,
    )
    completed = client.post(
        f"/mail-pool/entries/{alice_claim['usable_email']['id']}/complete",
        json={"project_key": "github"},
        headers=alice_headers,
    )
    same_project = client.post(
        "/mail-pool/claim",
        json={"project_key": "github", "claim_key": "alice-task-3"},
        headers=alice_headers,
    )
    other_project = client.post(
        "/mail-pool/claim",
        json={"project_key": "stripe", "claim_key": "alice-task-4"},
        headers=alice_headers,
    )
    cooled = client.post(
        f"/mail-pool/entries/{alice_claim['usable_email']['id']}/cooldown",
        headers=alice_headers,
    )
    after_cooldown = client.post(
        "/mail-pool/claim",
        json={"project_key": "stripe", "claim_key": "alice-task-5"},
        headers=alice_headers,
    )
    alice_entries = client.get("/mail-pool/entries", headers=alice_headers)
    bob_entries = client.get("/mail-pool/entries", headers=bob_headers)

    assert alice_claim["usable_email"]["id"] == alice_email["id"]
    assert bob_claim["usable_email"]["id"] == bob_email["id"]
    assert released.json()["status"] == "available"
    assert reclaimed.json()["usable_email"]["id"] == alice_email["id"]
    assert completed.json()["status"] == "completed"
    assert same_project.status_code == 404
    assert other_project.json()["usable_email"]["id"] == alice_email["id"]
    assert cooled.json()["status"] == "cooling"
    assert after_cooldown.status_code == 404
    assert [entry["usable_email"]["id"] for entry in alice_entries.json()["entries"]] == [
        alice_email["id"]
    ]
    assert [entry["usable_email"]["id"] for entry in bob_entries.json()["entries"]] == [
        bob_email["id"]
    ]
