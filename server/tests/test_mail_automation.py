from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.mail.email_accounts import add_email_account
from hx_email.server.mail.impl.email_fetch_service import fetch_all_active_accounts
from hx_email.server.mail.verification import EmailAccountMailbox, MailboxMessage
from hx_email.server.workspace.groups import create_group
from hx_email.server.workspace.notifications import set_group_polling

API = "/api/v1"


class CountingMailboxProvider:
    def __init__(self) -> None:
        self.calls: int = 0

    def read_messages(
        self,
        email_account: EmailAccountMailbox,
        folder: str = "inbox",
        skip: int = 0,
        top: int = 50,
        since_uid: str = "",
    ) -> list[MailboxMessage]:
        _ = (email_account, folder, skip, top, since_uid)
        self.calls += 1
        return [
            MailboxMessage(
                recipient_address="owner@example.com",
                from_address="sender@example.com",
                subject="New mail",
                body="Hello",
                received_at="2026-08-01T10:00:00Z",
                message_id="101",
            )
        ]


def login_admin(client: TestClient, settings: Settings) -> dict[str, str]:
    response = client.post(
        f"{API}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_automatic_polling_skips_disabled_groups(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    group = create_group(settings, 1, "quiet", "#58a6ff")
    add_email_account(
        settings,
        1,
        "imap",
        "owner@example.com",
        "Owner",
        "8.8.8.8",
        993,
        "owner@example.com",
        "password",
        "",
        "",
        [],
        group.id,
    )
    provider = CountingMailboxProvider()
    assert set_group_polling(settings, 1, group.id, False)

    disabled_summary = fetch_all_active_accounts(settings, provider)
    assert provider.calls == 0
    assert disabled_summary["messages_stored"] == 0

    assert set_group_polling(settings, 1, group.id, True)
    enabled_summary = fetch_all_active_accounts(settings, provider)
    assert provider.calls == 1
    assert enabled_summary["messages_stored"] == 1


def test_settings_enable_pool_generates_key_and_validate_interval(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)

    enabled = client.put(
        f"{API}/settings",
        json={"pool_external_enabled": True},
        headers=headers,
    )
    invalid = client.put(
        f"{API}/settings",
        json={"polling_interval": 1},
        headers=headers,
    )

    assert enabled.status_code == 200
    assert enabled.json()["pool_external_enabled"] == "true"
    assert len(enabled.json()["external_api_key"]) >= 32
    assert invalid.status_code == 422
    assert "polling_interval" in invalid.json()["detail"]


def test_non_admin_cannot_change_system_automation_settings(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    admin_headers = login_admin(client, settings)
    client.put(
        f"{API}/admin/settings/registration",
        json={"enabled": True},
        headers=admin_headers,
    )
    registration = client.post(
        f"{API}/auth/register",
        json={"username": "member", "password": "member-password"},
    )
    member_headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}

    response = client.put(
        f"{API}/settings",
        json={"enable_auto_polling": True, "polling_interval": 10},
        headers=member_headers,
    )
    settings_read = client.get(f"{API}/settings", headers=member_headers)
    script_test = client.post(
        f"{API}/settings/script-test",
        json={"path": "/tmp/notify.sh", "timeout_seconds": 5},
        headers=member_headers,
    )

    assert response.status_code == 403
    assert settings_read.status_code == 403
    assert script_test.status_code == 403
    current = client.get(f"{API}/settings", headers=admin_headers).json()
    assert current["enable_auto_polling"] == "false"
    assert current["polling_interval"] == "30"


def test_latest_messages_are_user_scoped(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)
    with connect(settings) as connection:
        connection.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES ('other', 'x', 0)"
        )
        other_user_id: int = int(
            connection.execute("SELECT id FROM users WHERE username = 'other'").fetchone()[0]
        )
        admin_email_id: int = int(
            connection.execute(
                "INSERT INTO usable_emails (user_id, address) VALUES (1, 'admin@example.com')"
            ).lastrowid
        )
        other_email_id: int = int(
            connection.execute(
                "INSERT INTO usable_emails (user_id, address) VALUES (?, 'other@example.com')",
                (other_user_id,),
            ).lastrowid
        )
        connection.execute(
            "INSERT INTO fetched_messages (user_id, usable_email_id, subject, body, body_hash)"
            " VALUES (1, ?, 'Admin mail', 'body', 'admin')",
            (admin_email_id,),
        )
        connection.execute(
            "INSERT INTO fetched_messages (user_id, usable_email_id, subject, body, body_hash)"
            " VALUES (?, ?, 'Other mail', 'body', 'other')",
            (other_user_id, other_email_id),
        )

    response = client.get(f"{API}/overview/latest-messages", headers=headers)

    assert response.status_code == 200
    assert [message["subject"] for message in response.json()["messages"]] == ["Admin mail"]
