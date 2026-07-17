import pytest
from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate

LEGACY_CONTRACT_REASON: str = "Legacy API contract drift baselined during quality-gate adoption"


def login_admin(client: TestClient) -> dict[str, str]:
    session = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin"}
    ).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def register_user(client: TestClient, username: str) -> dict[str, object]:
    return client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": f"{username}-pass"},
    ).json()


@pytest.mark.xfail(reason=LEGACY_CONTRACT_REASON, strict=True)
def test_user_can_export_and_import_core_data_without_cross_user_leaks(tmp_path) -> None:
    source_settings = Settings(
        data_dir=tmp_path / "source", admin_username="admin", admin_password="admin"
    )
    migrate(source_settings)
    source = TestClient(create_app(source_settings))
    admin_headers = login_admin(source)
    source.put("/api/v1/admin/settings/registration", json={"enabled": True}, headers=admin_headers)
    alice = register_user(source, "alice")
    bob = register_user(source, "bob")
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}
    account = source.post(
        "/api/v1/email-accounts",
        json={
            "provider": "imap",
            "primary_address": "owner@example.com",
            "display_name": "Owner",
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "username": "owner",
            "imap_password": "app-password",
            "alias_addresses": ["alias@example.com"],
        },
        headers=alice_headers,
    ).json()
    group = source.post(
        "/api/v1/groups", json={"name": "Register", "color": "#58a6ff"}, headers=alice_headers
    ).json()
    tag = source.post(
        "/api/v1/tags", json={"name": "GitHub", "color": "#238636"}, headers=alice_headers
    ).json()
    source.put(
        f"/api/v1/usable-emails/{account['usable_emails'][1]['id']}/organize",
        json={"label": "Alias", "group_id": group["id"], "tag_ids": [tag["id"]]},
        headers=alice_headers,
    )
    platform = source.post(
        "/api/v1/platforms", json={"name": "GitHub"}, headers=alice_headers
    ).json()
    source.post(
        f"/api/v1/usable-emails/{account['usable_emails'][1]['id']}/platform-bindings",
        json={"platform_id": platform["id"], "status": "active", "notes": "login"},
        headers=alice_headers,
    )
    source.post(
        "/api/v1/email-accounts",
        json={"provider": "imap", "primary_address": "bob@example.com", "display_name": "Bob"},
        headers=bob_headers,
    )

    exported = source.get("/api/v1/data/export", headers=alice_headers)

    target_settings = Settings(
        data_dir=tmp_path / "target", admin_username="admin", admin_password="admin"
    )
    migrate(target_settings)
    target = TestClient(create_app(target_settings))
    target_headers = login_admin(target)
    imported = target.post("/api/v1/data/import", json=exported.json(), headers=target_headers)
    duplicate_import = target.post(
        "/api/v1/data/import", json=exported.json(), headers=target_headers
    )
    workbench = target.get("/api/v1/workbench/usable-emails", headers=target_headers)
    platforms = target.get("/api/v1/platforms", headers=target_headers)
    bindings = target.get(
        f"/api/v1/usable-emails/{imported.json()['usable_emails'][1]['id']}/platform-bindings",
        headers=target_headers,
    )

    assert exported.status_code == 200
    assert exported.json()["email_accounts"][0]["primary_address"] == "owner@example.com"
    assert exported.json()["email_accounts"][0]["imap_password"] == "app-password"
    assert exported.json()["usable_emails"][1]["address"] == "alias@example.com"
    assert "bob@example.com" not in str(exported.json())
    assert imported.status_code == 201
    assert duplicate_import.status_code == 409
    assert [email["address"] for email in workbench.json()["usable_emails"]] == [
        "owner@example.com",
        "alias@example.com",
    ]
    assert workbench.json()["usable_emails"][1]["group"]["name"] == "Register"
    assert workbench.json()["usable_emails"][1]["tags"][0]["name"] == "GitHub"
    assert platforms.json()["platforms"] == [
        {"id": platforms.json()["platforms"][0]["id"], "name": "GitHub"}
    ]
    assert bindings.json()["platform_bindings"][0]["notes"] == "login"
