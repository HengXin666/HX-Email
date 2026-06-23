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


def test_email_account_can_manage_real_alias_usable_emails(tmp_path):
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
            "alias_addresses": ["alias-one@example.com", "alias-two@example.com"],
        },
        headers=headers,
    )
    add_alias = client.post(
        f"/email-accounts/{created.json()['id']}/aliases",
        json={"address": "alias-three@example.com", "label": "Alias Three"},
        headers=headers,
    )
    plus_alias = client.post(
        f"/email-accounts/{created.json()['id']}/aliases",
        json={"address": "owner+tag@example.com", "label": "Plus tag"},
        headers=headers,
    )
    duplicate_primary = client.post(
        f"/email-accounts/{created.json()['id']}/aliases",
        json={"address": "owner@example.com", "label": "Duplicate primary"},
        headers=headers,
    )
    detail = client.get(f"/email-accounts/{created.json()['id']}", headers=headers)
    deactivate_alias = client.post(
        f"/usable-emails/{add_alias.json()['id']}/deactivate",
        headers=headers,
    )
    workbench_after = client.get("/usable-emails", headers=headers)

    assert created.status_code == 201
    assert [email["kind"] for email in created.json()["usable_emails"]] == [
        "primary",
        "alias",
        "alias",
    ]
    assert add_alias.status_code == 201
    assert add_alias.json()["kind"] == "alias"
    assert plus_alias.status_code == 422
    assert duplicate_primary.status_code == 409
    assert detail.status_code == 200
    assert [email["address"] for email in detail.json()["usable_emails"]] == [
        "owner@example.com",
        "alias-one@example.com",
        "alias-two@example.com",
        "alias-three@example.com",
    ]
    assert deactivate_alias.status_code == 200
    assert deactivate_alias.json()["status"] == "inactive"
    assert [email["address"] for email in workbench_after.json()["usable_emails"]] == [
        "owner@example.com",
        "alias-one@example.com",
        "alias-two@example.com",
    ]


def test_deactivating_email_account_deactivates_aliases_without_cross_user_leaks(tmp_path):
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
    alice = register_user(client, "alice")
    bob = register_user(client, "bob")
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}

    alice_account = client.post(
        "/email-accounts",
        json={
            "provider": "imap",
            "primary_address": "alice@example.com",
            "display_name": "Alice",
            "alias_addresses": ["shared-alias@example.com"],
        },
        headers=alice_headers,
    )
    bob_account = client.post(
        "/email-accounts",
        json={
            "provider": "imap",
            "primary_address": "bob@example.com",
            "display_name": "Bob",
            "alias_addresses": ["shared-alias@example.com"],
        },
        headers=bob_headers,
    )

    deactivate = client.post(
        f"/email-accounts/{alice_account.json()['id']}/deactivate",
        headers=alice_headers,
    )
    alice_workbench = client.get("/usable-emails", headers=alice_headers)
    bob_workbench = client.get("/usable-emails", headers=bob_headers)

    assert alice_account.status_code == 201
    assert bob_account.status_code == 201
    assert deactivate.status_code == 200
    assert alice_workbench.json() == {"usable_emails": []}
    assert [email["address"] for email in bob_workbench.json()["usable_emails"]] == [
        "bob@example.com",
        "shared-alias@example.com",
    ]
