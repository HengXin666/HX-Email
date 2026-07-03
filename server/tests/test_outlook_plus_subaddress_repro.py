from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate
from hx_email.server.mail import EmailAccountMailbox, MailboxMessage

API = "/api/v1"


class OutlookCanonicalRecipientProvider:
    def read_messages(self, email_account: EmailAccountMailbox) -> list[MailboxMessage]:
        assert email_account.primary_address == "yyy@outlook.com"
        return [
            MailboxMessage(
                recipient_address="yyy@outlook.com",
                subject="Outlook plus subaddress verification",
                body="Your code is 918273",
                received_at="2026-07-04 10:00:00",
            )
        ]


class OutlookPlusRecipientProvider:
    def read_messages(self, email_account: EmailAccountMailbox) -> list[MailboxMessage]:
        assert email_account.primary_address == "yyy@outlook.com"
        return [
            MailboxMessage(
                recipient_address="yyy+wd@outlook.com",
                subject="Outlook plus recipient verification",
                body="Your code is 827364",
                received_at="2026-07-04 10:01:00",
            )
        ]


def create_outlook_account(
    client: TestClient,
    headers: dict[str, str],
) -> dict[str, object]:
    return client.post(
        f"{API}/email-accounts",
        json={
            "provider": "outlook",
            "primary_address": "yyy@outlook.com",
            "display_name": "Outlook",
        },
        headers=headers,
    ).json()


def login(client: TestClient, settings: Settings) -> dict[str, str]:
    session = client.post(
        f"{API}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    ).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def test_outlook_plus_subaddress_can_read_when_provider_returns_primary_recipient(
    tmp_path,
) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    provider = OutlookCanonicalRecipientProvider()
    client = TestClient(create_app(settings, mailbox_provider=provider))
    headers = login(client, settings)

    create_outlook_account(client, headers)
    plus_email = client.post(
        f"{API}/usable-emails",
        json={"address": "yyy+xxx@outlook.com", "label": "Plus xxx"},
        headers=headers,
    ).json()

    response = client.post(
        f"{API}/usable-emails/{plus_email['id']}/verification/read",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["usable_email"]["address"] == "yyy+xxx@outlook.com"
    assert [match["code"] for match in response.json()["matches"]] == ["918273"]


def test_outlook_primary_verification_includes_plus_recipient_content(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    provider = OutlookPlusRecipientProvider()
    client = TestClient(create_app(settings, mailbox_provider=provider))
    headers = login(client, settings)
    account = create_outlook_account(client, headers)
    primary_id = int(account["primary_usable_email"]["id"])

    response = client.post(
        f"{API}/usable-emails/{primary_id}/verification/read",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["usable_email"]["address"] == "yyy@outlook.com"
    assert [match["code"] for match in response.json()["matches"]] == ["827364"]


def test_outlook_primary_messages_include_plus_recipient_content(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    provider = OutlookPlusRecipientProvider()
    client = TestClient(create_app(settings, mailbox_provider=provider))
    headers = login(client, settings)
    account = create_outlook_account(client, headers)
    primary_id = int(account["primary_usable_email"]["id"])

    fetched = client.post(f"{API}/usable-emails/{primary_id}/fetch-emails", headers=headers)
    messages = client.get(f"{API}/usable-emails/{primary_id}/messages", headers=headers)

    assert fetched.status_code == 200
    assert fetched.json()["messages_stored"] == 1
    assert [msg["recipient_address"] for msg in messages.json()["messages"]] == [
        "yyy+wd@outlook.com"
    ]
