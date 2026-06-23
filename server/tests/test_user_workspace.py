from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate


def test_users_only_see_usable_emails_in_their_own_workspace(tmp_path):
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
    alice_session = client.post(
        "/auth/register",
        json={"username": "alice", "password": "alice-pass"},
    ).json()
    bob_session = client.post(
        "/auth/register",
        json={"username": "bob", "password": "bob-pass"},
    ).json()

    alice_headers = {"Authorization": f"Bearer {alice_session['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob_session['access_token']}"}
    alice_create = client.post(
        "/usable-emails",
        json={"address": "shared@example.com", "label": "Alice"},
        headers=alice_headers,
    )
    bob_create = client.post(
        "/usable-emails",
        json={"address": "shared@example.com", "label": "Bob"},
        headers=bob_headers,
    )

    alice_list = client.get("/usable-emails", headers=alice_headers)
    bob_list = client.get("/usable-emails", headers=bob_headers)

    assert alice_create.status_code == 201
    assert bob_create.status_code == 201
    assert alice_list.json() == {
        "usable_emails": [
            {
                "id": alice_create.json()["id"],
                "address": "shared@example.com",
                "label": "Alice",
                "kind": "custom",
                "status": "active",
            }
        ]
    }
    assert bob_list.json() == {
        "usable_emails": [
            {
                "id": bob_create.json()["id"],
                "address": "shared@example.com",
                "label": "Bob",
                "kind": "custom",
                "status": "active",
            }
        ]
    }
