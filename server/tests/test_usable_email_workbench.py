from fastapi.testclient import TestClient

from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate


def login_admin(client: TestClient) -> dict[str, str]:
    session = client.post("/auth/login", json={"username": "admin", "password": "admin"}).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def create_account(client: TestClient, headers: dict[str, str], primary: str, aliases: list[str]):
    return client.post(
        "/email-accounts",
        json={
            "provider": "imap",
            "primary_address": primary,
            "display_name": primary,
            "alias_addresses": aliases,
        },
        headers=headers,
    ).json()


def test_workbench_filters_usable_emails_by_kind_group_tag_keyword_and_paginates(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client)

    account = create_account(
        client,
        headers,
        "owner@example.com",
        ["campaign@example.com", "billing@example.com"],
    )
    group = client.post(
        "/groups",
        json={"name": "注册用途", "color": "#58a6ff"},
        headers=headers,
    ).json()
    tag = client.post(
        "/tags",
        json={"name": "验证码", "color": "#238636"},
        headers=headers,
    ).json()
    campaign_alias = account["usable_emails"][1]
    client.put(
        f"/usable-emails/{campaign_alias['id']}/organize",
        json={"label": "Campaign alias", "group_id": group["id"], "tag_ids": [tag["id"]]},
        headers=headers,
    )

    response = client.get(
        "/workbench/usable-emails",
        params={
            "kind": "alias",
            "status": "active",
            "group_id": group["id"],
            "tag_id": tag["id"],
            "keyword": "campaign",
            "platform_binding": "unbound",
            "page": 1,
            "page_size": 1,
        },
        headers=headers,
    )
    next_page = client.get(
        "/workbench/usable-emails",
        params={"kind": "alias", "page": 2, "page_size": 1},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "usable_emails": [
            {
                "id": campaign_alias["id"],
                "address": "campaign@example.com",
                "label": "Campaign alias",
                "kind": "alias",
                "status": "active",
                "group": {"id": group["id"], "name": "注册用途", "color": "#58a6ff"},
                "tags": [{"id": tag["id"], "name": "验证码", "color": "#238636"}],
                "platform_binding_count": 0,
            }
        ],
        "total": 1,
        "page": 1,
        "page_size": 1,
    }
    assert next_page.status_code == 200
    assert next_page.json()["total"] == 2
    assert [email["address"] for email in next_page.json()["usable_emails"]] == [
        "billing@example.com"
    ]


def test_workbench_filters_are_isolated_to_current_user(tmp_path):
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    admin_headers = login_admin(client)
    client.put(
        "/admin/settings/registration",
        json={"enabled": True},
        headers=admin_headers,
    )
    alice = client.post("/auth/register", json={"username": "alice", "password": "alice-pass"}).json()
    bob = client.post("/auth/register", json={"username": "bob", "password": "bob-pass"}).json()
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}

    alice_account = create_account(client, alice_headers, "alice@example.com", ["shared@example.com"])
    bob_account = create_account(client, bob_headers, "bob@example.com", ["shared@example.com"])
    alice_group = client.post(
        "/groups",
        json={"name": "Alice Group", "color": "#58a6ff"},
        headers=alice_headers,
    ).json()
    bob_group = client.post(
        "/groups",
        json={"name": "Bob Group", "color": "#238636"},
        headers=bob_headers,
    ).json()
    client.put(
        f"/usable-emails/{alice_account['usable_emails'][1]['id']}/organize",
        json={"group_id": alice_group["id"], "tag_ids": []},
        headers=alice_headers,
    )
    client.put(
        f"/usable-emails/{bob_account['usable_emails'][1]['id']}/organize",
        json={"group_id": bob_group["id"], "tag_ids": []},
        headers=bob_headers,
    )

    alice_response = client.get(
        "/workbench/usable-emails",
        params={"group_id": alice_group["id"], "keyword": "shared"},
        headers=alice_headers,
    )
    bob_response = client.get(
        "/workbench/usable-emails",
        params={"group_id": alice_group["id"], "keyword": "shared"},
        headers=bob_headers,
    )

    assert [email["address"] for email in alice_response.json()["usable_emails"]] == [
        "shared@example.com"
    ]
    assert bob_response.json()["usable_emails"] == []
