from urllib.parse import parse_qs, urlparse

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


def test_email_accounts_can_be_listed_for_current_workspace(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    session = client.post(
        "/auth/login",
        json={"username": "admin", "password": "admin"},
    ).json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    client.post(
        "/email-accounts",
        json={
            "provider": "imap",
            "primary_address": "owner@example.com",
            "display_name": "Owner",
            "alias_addresses": ["alias@example.com"],
        },
        headers=headers,
    )
    response = client.get("/email-accounts", headers=headers)

    assert response.status_code == 200
    assert response.json()["email_accounts"][0]["primary_address"] == "owner@example.com"
    assert [
        email["address"] for email in response.json()["email_accounts"][0]["usable_emails"]
    ] == [
        "owner@example.com",
        "alias@example.com",
    ]


def test_importing_reference_account_text_supports_imap_and_outlook(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    session = client.post(
        "/auth/login",
        json={"username": "admin", "password": "admin"},
    ).json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    imported = client.post(
        "/email-accounts/import",
        json={
            "text": "\n".join(
                [
                    "person@gmail.com----gmail-app-pass",
                    "person@qq.com----qq-auth-code----qq",
                    "person@custom.test----custom-pass----custom----imap.custom.test----1993",
                    "person@outlook.com----unused-pass----client-id----refresh-token",
                ]
            )
        },
        headers=headers,
    )
    accounts = client.get("/email-accounts", headers=headers)
    exported = client.get("/email-accounts/export-text", headers=headers)

    assert imported.status_code == 201
    assert imported.json()["imported"] == 4
    assert [account["provider"] for account in accounts.json()["email_accounts"]] == [
        "gmail",
        "qq",
        "custom",
        "outlook",
    ]
    assert accounts.json()["email_accounts"][3]["has_refresh_token"] is True
    assert "person@gmail.com----gmail-app-pass----gmail" in exported.text
    assert "person@outlook.com----unused-pass----client-id----refresh-token" in exported.text


def test_outlook_two_segment_import_is_rejected(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    session = client.post(
        "/auth/login",
        json={"username": "admin", "password": "admin"},
    ).json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    imported = client.post(
        "/email-accounts/import",
        json={"text": "person@outlook.com----password"},
        headers=headers,
    )

    assert imported.status_code == 201
    assert imported.json()["imported"] == 0
    assert imported.json()["failed"] == 1
    assert "Outlook accounts must use" in imported.json()["errors"][0]["error"]


def test_token_tool_prepare_and_save_updates_outlook_credentials(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    session = client.post(
        "/auth/login",
        json={"username": "admin", "password": "admin"},
    ).json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    account = client.post(
        "/email-accounts",
        json={
            "provider": "outlook",
            "primary_address": "person@outlook.com",
            "display_name": "Outlook",
        },
        headers=headers,
    ).json()

    prepared = client.post(
        "/token-tool/prepare",
        json={
            "client_id": "client-id",
            "redirect_uri": "http://localhost",
            "scope": "offline_access https://graph.microsoft.com/Mail.Read",
            "tenant": "consumers",
            "prompt_consent": True,
        },
        headers=headers,
    )
    saved = client.post(
        "/token-tool/save",
        json={
            "account_id": account["id"],
            "client_id": "client-id",
            "refresh_token": "refresh-token",
        },
        headers=headers,
    )
    detail = client.get(f"/email-accounts/{account['id']}", headers=headers)

    assert prepared.status_code == 200
    assert "login.microsoftonline.com/consumers" in prepared.json()["data"]["authorize_url"]
    assert "state=" in prepared.json()["data"]["authorize_url"]
    assert saved.status_code == 200
    assert detail.json()["client_id"] == "client-id"
    assert detail.json()["has_refresh_token"] is True


def test_token_tool_config_callback_accounts_and_create_flow(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    session = client.post(
        "/auth/login",
        json={"username": "admin", "password": "admin"},
    ).json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    config = client.get("/token-tool/config", headers=headers)
    saved_config = client.post(
        "/token-tool/config",
        json={
            "client_id": "client-id",
            "redirect_uri": "http://localhost:8000/token-tool/callback",
            "scope": "offline_access https://graph.microsoft.com/Mail.Read",
            "tenant": "consumers",
            "prompt_consent": True,
        },
        headers=headers,
    )
    prepared = client.post(
        "/token-tool/prepare",
        json=saved_config.json()["data"],
        headers=headers,
    )
    callback = client.get(
        "/token-tool/callback",
        params={"code": "auth-code", "state": prepared.json()["data"]["state"]},
    )
    created = client.post(
        "/token-tool/save",
        json={
            "mode": "create",
            "email": "created@outlook.com",
            "client_id": "client-id",
            "refresh_token": "refresh-token",
        },
        headers=headers,
    )
    accounts = client.get("/token-tool/accounts", headers=headers)

    assert config.status_code == 200
    assert config.json()["data"]["tenant"] == "consumers"
    assert config.json()["data"]["scope"] == (
        "offline_access https://outlook.office.com/IMAP.AccessAsUser.All"
    )
    assert saved_config.status_code == 200
    assert prepared.status_code == 200
    authorize_params = parse_qs(urlparse(prepared.json()["data"]["authorize_url"]).query)
    assert authorize_params["redirect_uri"] == ["http://localhost:8000/token-tool/callback"]
    assert callback.status_code == 200
    assert "授权成功" in callback.text
    assert created.status_code == 200
    assert accounts.json()["data"] == [
        {
            "id": created.json()["data"]["account_id"],
            "email": "created@outlook.com",
            "status": "active",
        }
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
