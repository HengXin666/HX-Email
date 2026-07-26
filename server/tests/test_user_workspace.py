from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate


def test_users_only_see_usable_emails_in_their_own_workspace(tmp_path):
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))

    admin_session = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin"},
    ).json()
    client.put(
        "/api/v1/admin/settings/registration",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {admin_session['access_token']}"},
    )
    alice_session = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "password": "alice-pass"},
    ).json()
    bob_session = client.post(
        "/api/v1/auth/register",
        json={"username": "bob", "password": "bob-pass"},
    ).json()

    alice_headers = {"Authorization": f"Bearer {alice_session['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob_session['access_token']}"}
    alice_create = client.post(
        "/api/v1/usable-emails",
        json={"address": "shared@example.com", "label": "Alice"},
        headers=alice_headers,
    )
    bob_create = client.post(
        "/api/v1/usable-emails",
        json={"address": "shared@example.com", "label": "Bob"},
        headers=bob_headers,
    )

    alice_list = client.get("/api/v1/usable-emails", headers=alice_headers)
    bob_list = client.get("/api/v1/usable-emails", headers=bob_headers)

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
                "group": None,
                "email_account_id": None,
                "notify_enabled": True,
                "last_refresh_at": None,
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
                "group": None,
                "email_account_id": None,
                "notify_enabled": True,
                "last_refresh_at": None,
            }
        ]
    }


def test_verification_state_is_not_visible_across_workspaces(tmp_path):
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))

    admin_session = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin"},
    ).json()
    client.put(
        "/api/v1/admin/settings/registration",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {admin_session['access_token']}"},
    )
    alice_session = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "password": "alice-pass"},
    ).json()
    bob_session = client.post(
        "/api/v1/auth/register",
        json={"username": "bob", "password": "bob-pass"},
    ).json()
    alice_headers = {"Authorization": f"Bearer {alice_session['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob_session['access_token']}"}

    alice_email = client.post(
        "/api/v1/usable-emails",
        json={"address": "alice-only@example.com", "label": "Alice"},
        headers=alice_headers,
    ).json()

    own_state = client.get(
        f"/api/v1/usable-emails/{alice_email['id']}/verification/state",
        headers=alice_headers,
    )
    cross_state = client.get(
        f"/api/v1/usable-emails/{alice_email['id']}/verification/state",
        headers=bob_headers,
    )

    assert own_state.status_code == 200
    assert own_state.json()["message_count"] == 0
    # 他人邮箱的验证码状态 (含 message_count) 不可探测
    assert cross_state.status_code == 404
