"""Regression tests: /api/v1/emails/* must be scoped to the requesting user."""

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate

API = "/api/v1"


class FakeMailboxProvider:
    def __init__(self, messages_by_address):
        self.messages_by_address = messages_by_address

    def read_messages(self, email_account, folder="inbox", skip=0, top=50):
        return self.messages_by_address.get(email_account.primary_address, [])


def _enable_registration(client: TestClient, settings: Settings) -> None:
    session = client.post(
        f"{API}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    ).json()
    client.put(
        f"{API}/admin/settings/registration",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {session['access_token']}"},
    )


def _register(client: TestClient, username: str) -> dict[str, str]:
    session = client.post(
        f"{API}/auth/register",
        json={"username": username, "password": f"{username}-pass"},
    ).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def _create_account(client: TestClient, headers: dict[str, str], address: str) -> dict[str, object]:
    return client.post(
        f"{API}/email-accounts",
        json={
            "provider": "imap",
            "primary_address": address,
            "display_name": address,
        },
        headers=headers,
    ).json()


def test_emails_endpoints_do_not_leak_other_users_mailboxes(tmp_path):
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    mailbox = FakeMailboxProvider(
        {
            "alice@example.com": [
                {
                    "recipient_address": "alice@example.com",
                    "subject": "Alice secret",
                    "body": "Your code is 481927. Confirm at https://service.test/alice",
                },
            ],
            "bob@example.com": [
                {
                    "recipient_address": "bob@example.com",
                    "subject": "Bob private",
                    "body": "Your code is 729315. Confirm at https://service.test/bob",
                },
            ],
        }
    )
    client = TestClient(create_app(settings, mailbox_provider=mailbox))
    _enable_registration(client, settings)
    alice_headers = _register(client, "alice")
    bob_headers = _register(client, "bob")
    alice_account = _create_account(client, alice_headers, "alice@example.com")
    bob_account = _create_account(client, bob_headers, "bob@example.com")

    alice_list = client.get(f"{API}/emails/alice@example.com", headers=alice_headers)
    bob_list = client.get(f"{API}/emails/alice@example.com", headers=bob_headers)
    bob_list_own = client.get(f"{API}/emails/bob@example.com", headers=bob_headers)

    assert alice_list.status_code == 200
    assert [email["subject"] for email in alice_list.json()["emails"]] == ["Alice secret"]
    assert bob_list.status_code == 200
    assert bob_list.json()["emails"] == []
    assert bob_list_own.status_code == 200
    assert [email["subject"] for email in bob_list_own.json()["emails"]] == ["Bob private"]

    alice_detail = client.get(f"{API}/emails/alice@example.com/1", headers=alice_headers).json()
    bob_detail = client.get(f"{API}/emails/alice@example.com/1", headers=bob_headers).json()
    assert alice_detail["body"] == "Your code is 481927. Confirm at https://service.test/alice"
    assert bob_detail["subject"] == ""
    assert bob_detail["body"] == ""

    alice_code = client.get(
        f"{API}/emails/alice@example.com/extract-verification", headers=alice_headers
    ).json()
    bob_code = client.get(
        f"{API}/emails/alice@example.com/extract-verification", headers=bob_headers
    ).json()
    assert alice_code["verification_code"] == "481927"
    assert bob_code["verification_code"] == ""
    assert bob_code["match_count"] == 0

    bob_batch = client.post(
        f"{API}/emails/batch",
        json={"account_ids": [alice_account["id"]]},
        headers=bob_headers,
    ).json()
    assert bob_batch["results"][0]["success"] is False
    assert bob_batch["results"][0]["error"] == "Account not found"

    alice_batch = client.post(
        f"{API}/emails/batch",
        json={"account_ids": [alice_account["id"], bob_account["id"]]},
        headers=alice_headers,
    ).json()
    assert [result["account_id"] for result in alice_batch["results"]] == [
        alice_account["id"],
        bob_account["id"],
    ]
    assert alice_batch["results"][0]["success"] is True
    assert alice_batch["results"][1]["success"] is False

    bob_delete = client.post(
        f"{API}/emails/delete",
        json={"email": "alice@example.com", "ids": ["1"]},
        headers=bob_headers,
    )
    assert bob_delete.status_code == 200
    assert bob_delete.json() == {"success": False, "deleted_count": 0}

    alice_delete = client.post(
        f"{API}/emails/delete",
        json={"email": "alice@example.com", "ids": ["1"]},
        headers=alice_headers,
    )
    assert alice_delete.json() == {"success": True, "deleted_count": 1}
