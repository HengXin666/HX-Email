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
    def __init__(self):
        self.created_for: list[str | None] = []
        self.messages_by_address: dict[str, list[FakeProviderMessage]] = {}

    def create_mailbox(self, requested_address: str | None = None):
        self.created_for.append(requested_address)
        return {
            "provider_mailbox_id": "cf-box-1",
            "address": requested_address or "issued@example.test",
        }

    def list_messages(self, provider_mailbox_id: str):
        return self.messages_by_address.get(provider_mailbox_id, [])


def login_admin(client: TestClient) -> dict[str, str]:
    session = client.post("/auth/login", json={"username": "admin", "password": "admin"}).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def register_user(client: TestClient, username: str) -> dict[str, object]:
    return client.post(
        "/auth/register",
        json={"username": username, "password": f"{username}-pass"},
    ).json()


def test_creating_cf_temp_mail_adds_temp_usable_email_without_email_account(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    provider = FakeCfTempMailProvider()
    client = TestClient(create_app(settings, temp_mail_providers={"cf": provider}))
    headers = login_admin(client)

    created = client.post(
        "/temp-mail/cf/mailboxes",
        json={"address": "signup@example.test", "label": "Signup temp"},
        headers=headers,
    )
    workbench = client.get(
        "/workbench/usable-emails",
        params={"kind": "temp"},
        headers=headers,
    )

    assert created.status_code == 201
    assert created.json() == {
        "id": created.json()["id"],
        "address": "signup@example.test",
        "label": "Signup temp",
        "kind": "temp",
        "status": "active",
        "provider": "cf",
        "email_account_id": None,
    }
    assert workbench.status_code == 200
    assert workbench.json()["usable_emails"] == [
        {
            "id": created.json()["id"],
            "address": "signup@example.test",
            "label": "Signup temp",
            "kind": "temp",
            "status": "active",
            "group": None,
            "tags": [],
            "platform_binding_count": 0,
        }
    ]
    assert provider.created_for == ["signup@example.test"]


def test_temp_mail_reads_messages_codes_and_verification_links_through_cf_provider(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    provider = FakeCfTempMailProvider()
    provider.messages_by_address["cf-box-1"] = [
        FakeProviderMessage(
            id="msg-1",
            from_address="noreply@service.test",
            subject="Your login code is 482913",
            text="Use 482913 or open https://service.test/verify?token=abc123",
        )
    ]
    client = TestClient(create_app(settings, temp_mail_providers={"cf": provider}))
    headers = login_admin(client)
    mailbox = client.post(
        "/temp-mail/cf/mailboxes",
        json={"address": "signup@example.test", "label": "Signup temp"},
        headers=headers,
    ).json()

    messages = client.get(f"/temp-mail/{mailbox['id']}/messages", headers=headers)
    codes = client.get(f"/temp-mail/{mailbox['id']}/codes", headers=headers)
    links = client.get(f"/temp-mail/{mailbox['id']}/verification-links", headers=headers)

    assert messages.status_code == 200
    assert messages.json()["messages"] == [
        {
            "id": "msg-1",
            "from_address": "noreply@service.test",
            "subject": "Your login code is 482913",
            "text": "Use 482913 or open https://service.test/verify?token=abc123",
            "html": "",
        }
    ]
    assert codes.status_code == 200
    assert codes.json() == {"codes": [{"message_id": "msg-1", "code": "482913"}]}
    assert links.status_code == 200
    assert links.json() == {
        "links": [{"message_id": "msg-1", "url": "https://service.test/verify?token=abc123"}]
    }


def test_temp_mail_is_isolated_by_user_and_can_be_deactivated_or_archived(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    provider = FakeCfTempMailProvider()
    client = TestClient(create_app(settings, temp_mail_providers={"cf": provider}))
    admin_headers = login_admin(client)
    client.put("/admin/settings/registration", json={"enabled": True}, headers=admin_headers)
    alice = register_user(client, "alice")
    bob = register_user(client, "bob")
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}

    alice_mailbox = client.post(
        "/temp-mail/cf/mailboxes",
        json={"address": "shared@example.test", "label": "Alice temp"},
        headers=alice_headers,
    ).json()
    bob_mailbox = client.post(
        "/temp-mail/cf/mailboxes",
        json={"address": "shared@example.test", "label": "Bob temp"},
        headers=bob_headers,
    )
    bob_archive_alice = client.post(
        f"/temp-mail/{alice_mailbox['id']}/archive",
        headers=bob_headers,
    )
    alice_archive = client.post(
        f"/temp-mail/{alice_mailbox['id']}/archive",
        headers=alice_headers,
    )
    bob_deactivate = client.post(
        f"/usable-emails/{bob_mailbox.json()['id']}/deactivate",
        headers=bob_headers,
    )
    alice_workbench = client.get(
        "/workbench/usable-emails",
        params={"kind": "temp", "status": "archived"},
        headers=alice_headers,
    )
    bob_workbench = client.get(
        "/workbench/usable-emails",
        params={"kind": "temp", "status": "inactive"},
        headers=bob_headers,
    )

    assert bob_mailbox.status_code == 201
    assert bob_archive_alice.status_code == 404
    assert alice_archive.status_code == 200
    assert alice_archive.json()["status"] == "archived"
    assert bob_deactivate.status_code == 200
    assert bob_deactivate.json()["status"] == "inactive"
    assert [email["address"] for email in alice_workbench.json()["usable_emails"]] == [
        "shared@example.test"
    ]
    assert [
        (email["address"], email["status"]) for email in bob_workbench.json()["usable_emails"]
    ] == [("shared@example.test", "inactive")]
