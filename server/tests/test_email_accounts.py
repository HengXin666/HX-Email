from fastapi.testclient import TestClient

from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate


def register_user(client: TestClient, username: str) -> dict[str, object]:
    return client.post(
        "/auth/register",
        json={"username": username, "password": f"{username}-pass"},
    ).json()


def test_adding_email_account_creates_primary_usable_email_in_current_workspace(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))

    admin_session = client.post(
        "/auth/login",
        json={"username": "admin", "password": "admin"},
    ).json()
    client.put(
        "/admin/settings/registration",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {admin_session['access_token']}"},
    )
    alice_session = register_user(client, "alice")
    bob_session = register_user(client, "bob")
    alice_headers = {"Authorization": f"Bearer {alice_session['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob_session['access_token']}"}

    alice_create = client.post(
        "/email-accounts",
        json={
            "provider": "imap",
            "primary_address": "shared@example.com",
            "display_name": "Alice IMAP",
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "username": "shared@example.com",
        },
        headers=alice_headers,
    )
    bob_create = client.post(
        "/email-accounts",
        json={
            "provider": "outlook_oauth",
            "primary_address": "shared@example.com",
            "display_name": "Bob Outlook",
        },
        headers=bob_headers,
    )
    alice_workbench = client.get("/usable-emails", headers=alice_headers)
    bob_workbench = client.get("/usable-emails", headers=bob_headers)

    assert alice_create.status_code == 201
    assert alice_create.json()["primary_usable_email"]["address"] == "shared@example.com"
    assert bob_create.status_code == 201
    assert alice_workbench.json()["usable_emails"] == [
        {
            "id": alice_create.json()["primary_usable_email"]["id"],
            "address": "shared@example.com",
            "label": "Alice IMAP",
            "kind": "primary",
            "status": "active",
        }
    ]
    assert bob_workbench.json()["usable_emails"] == [
        {
            "id": bob_create.json()["primary_usable_email"]["id"],
            "address": "shared@example.com",
            "label": "Bob Outlook",
            "kind": "primary",
            "status": "active",
        }
    ]


def test_deactivating_email_account_deactivates_primary_usable_email(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    session = client.post(
        "/auth/login",
        json={"username": "admin", "password": "admin"},
    ).json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    created = client.post(
        "/email-accounts",
        json={
            "provider": "imap",
            "primary_address": "owner@example.com",
            "display_name": "Owner",
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "username": "owner@example.com",
        },
        headers=headers,
    ).json()

    detail_before = client.get(
        f"/usable-emails/{created['primary_usable_email']['id']}",
        headers=headers,
    )
    deactivate = client.post(f"/email-accounts/{created['id']}/deactivate", headers=headers)
    workbench_after = client.get("/usable-emails", headers=headers)
    detail_after = client.get(
        f"/usable-emails/{created['primary_usable_email']['id']}",
        headers=headers,
    )

    assert detail_before.status_code == 200
    assert detail_before.json()["status"] == "active"
    assert deactivate.status_code == 200
    assert deactivate.json()["status"] == "inactive"
    assert workbench_after.json() == {"usable_emails": []}
    assert detail_after.status_code == 200
    assert detail_after.json()["status"] == "inactive"
