from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate


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


def test_admin_can_export_and_import_core_data_without_cross_user_leaks(tmp_path) -> None:
    source_settings = Settings(
        data_dir=tmp_path / "source", admin_username="admin", admin_password="admin"
    )
    migrate(source_settings)
    source = TestClient(create_app(source_settings))
    admin_headers = login_admin(source)
    source.put("/api/v1/admin/settings/registration", json={"enabled": True}, headers=admin_headers)
    alice = register_user(source, "alice")
    bob = register_user(source, "bob")
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    assert source.get("/api/v1/data/export", headers=alice_headers).status_code == 403
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
        headers=admin_headers,
    ).json()
    group = source.post(
        "/api/v1/groups", json={"name": "Register", "color": "#58a6ff"}, headers=admin_headers
    ).json()
    source.put(
        f"/api/v1/groups/{group['id']}/notify",
        json={"enabled": False},
        headers=admin_headers,
    )
    source.put(
        f"/api/v1/groups/{group['id']}/polling",
        json={"enabled": False},
        headers=admin_headers,
    )
    tag = source.post(
        "/api/v1/tags", json={"name": "GitHub", "color": "#238636"}, headers=admin_headers
    ).json()
    source.put(
        f"/api/v1/usable-emails/{account['usable_emails'][1]['id']}/organize",
        json={"label": "Alias", "group_id": group["id"], "tag_ids": [tag["id"]]},
        headers=admin_headers,
    )
    platform = source.post(
        "/api/v1/platforms", json={"name": "GitHub"}, headers=admin_headers
    ).json()
    source.post(
        f"/api/v1/usable-emails/{account['usable_emails'][1]['id']}/platform-bindings",
        json={"platform_id": platform["id"], "status": "active", "notes": "login"},
        headers=admin_headers,
    )
    source.post(
        "/api/v1/email-accounts",
        json={"provider": "imap", "primary_address": "bob@example.com", "display_name": "Bob"},
        headers=bob_headers,
    )

    exported = source.get("/api/v1/data/export", headers=admin_headers)

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
    assert exported.json()["groups"][0]["notify_enabled"] == 0
    assert exported.json()["groups"][0]["polling_enabled"] == 0
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
        {"id": platforms.json()["platforms"][0]["id"], "name": "GitHub", "binding_count": 1}
    ]
    assert bindings.json()["platform_bindings"][0]["notes"] == "login"
    assert imported.json()["groups"][0]["notify_enabled"] == 0
    assert imported.json()["groups"][0]["polling_enabled"] == 0


def test_export_import_round_trips_group_proxy_and_account_metadata(tmp_path) -> None:
    source_settings = Settings(
        data_dir=tmp_path / "source", admin_username="admin", admin_password="admin"
    )
    migrate(source_settings)
    source = TestClient(create_app(source_settings))
    headers = login_admin(source)
    group = source.post(
        "/api/v1/groups",
        json={"name": "Proxied", "color": "#ff0000", "proxy_url": "http://8.8.8.8:7890"},
        headers=headers,
    ).json()
    account = source.post(
        "/api/v1/email-accounts",
        json={
            "provider": "imap",
            "primary_address": "owner@example.com",
            "display_name": "Owner",
            "imap_host": "imap.example.com",
            "imap_port": 993,
        },
        headers=headers,
    ).json()
    source.put(
        f"/api/v1/email-accounts/{account['id']}",
        json={"group_id": group["id"], "remark": "vip account"},
        headers=headers,
    )

    exported = source.get("/api/v1/data/export", headers=headers).json()

    assert exported["groups"][0]["proxy_url"] == "http://8.8.8.8:7890"
    assert exported["email_accounts"][0]["remark"] == "vip account"
    assert exported["email_accounts"][0]["group_id"] == group["id"]

    target_settings = Settings(
        data_dir=tmp_path / "target", admin_username="admin", admin_password="admin"
    )
    migrate(target_settings)
    target = TestClient(create_app(target_settings))
    target_headers = login_admin(target)
    imported = target.post("/api/v1/data/import", json=exported, headers=target_headers)
    assert imported.status_code == 201

    re_exported = target.get("/api/v1/data/export", headers=target_headers).json()
    assert re_exported["groups"][0]["proxy_url"] == "http://8.8.8.8:7890"
    assert re_exported["email_accounts"][0]["remark"] == "vip account"
    assert re_exported["email_accounts"][0]["group_id"] == re_exported["groups"][0]["id"]


def test_import_with_dangling_references_returns_422_and_imports_nothing(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client)

    payload = {
        "version": 1,
        "email_accounts": [],
        "usable_emails": [
            {"id": 1, "email_account_id": None, "address": "a@example.com", "label": "A"}
        ],
        "groups": [],
        "tags": [],
        "usable_email_tags": [{"usable_email_id": 1, "tag_id": 999}],
        "platforms": [],
        "platform_bindings": [],
    }
    response = client.post("/api/v1/data/import", json=payload, headers=headers)

    assert response.status_code == 422
    assert "tag" in response.json()["detail"]
    # 失败的导入必须整体回滚, 不留下半套数据
    workbench = client.get("/api/v1/usable-emails", headers=headers)
    assert workbench.json() == {"usable_emails": []}
