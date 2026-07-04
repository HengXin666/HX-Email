from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate

API = "/api/v1"


class ApiClient:
    def __init__(self, client):
        self.client = client

    def post(self, path, **kwargs):
        return self.client.post(f"{API}{path}", **kwargs)

    def get(self, path, **kwargs):
        return self.client.get(f"{API}{path}", **kwargs)

    def put(self, path, **kwargs):
        return self.client.put(f"{API}{path}", **kwargs)

    def delete(self, path, **kwargs):
        return self.client.delete(f"{API}{path}", **kwargs)


def authenticated_client(tmp_path):
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = ApiClient(TestClient(create_app(settings)))
    session = client.post(
        "/auth/login",
        json={"username": "admin", "password": "admin"},
    ).json()
    return client, {"Authorization": f"Bearer {session['access_token']}"}


def test_user_can_create_search_and_update_platforms_with_case_sensitive_names(tmp_path):
    client, headers = authenticated_client(tmp_path)

    github = client.post("/platforms", json={"name": "GitHub"}, headers=headers)
    lowercase_github = client.post("/platforms", json={"name": "github"}, headers=headers)
    duplicate = client.post("/platforms", json={"name": "GitHub"}, headers=headers)
    search = client.get("/platforms", params={"q": "git"}, headers=headers)
    update = client.put(
        f"/platforms/{github.json()['id']}",
        json={"name": "GitHub Enterprise"},
        headers=headers,
    )

    assert github.status_code == 201
    assert github.json() == {"id": github.json()["id"], "name": "GitHub", "binding_count": 0}
    assert lowercase_github.status_code == 201
    assert duplicate.status_code == 409
    assert search.status_code == 200
    assert search.json() == {
        "platforms": [
            {"id": github.json()["id"], "name": "GitHub", "binding_count": 0},
            {"id": lowercase_github.json()["id"], "name": "github", "binding_count": 0},
        ]
    }
    assert update.status_code == 200
    assert update.json() == {
        "id": github.json()["id"],
        "name": "GitHub Enterprise",
        "binding_count": 0,
    }


def test_user_can_bind_usable_emails_to_platforms_with_status_and_notes(tmp_path):
    client, headers = authenticated_client(tmp_path)
    email_one = client.post(
        "/usable-emails",
        json={"address": "one@example.com", "label": "One"},
        headers=headers,
    ).json()
    email_two = client.post(
        "/usable-emails",
        json={"address": "two@example.com", "label": "Two"},
        headers=headers,
    ).json()
    github = client.post("/platforms", json={"name": "GitHub"}, headers=headers).json()
    stripe = client.post("/platforms", json={"name": "Stripe"}, headers=headers).json()

    github_binding = client.post(
        f"/usable-emails/{email_one['id']}/platform-bindings",
        json={"platform_id": github["id"], "status": "active", "notes": "primary login"},
        headers=headers,
    )
    stripe_binding = client.post(
        f"/usable-emails/{email_one['id']}/platform-bindings",
        json={"platform_id": stripe["id"], "status": "risk", "notes": "chargeback watch"},
        headers=headers,
    )
    second_email_github = client.post(
        f"/usable-emails/{email_two['id']}/platform-bindings",
        json={"platform_id": github["id"], "status": "pending_verification", "notes": ""},
        headers=headers,
    )
    duplicate = client.post(
        f"/usable-emails/{email_one['id']}/platform-bindings",
        json={"platform_id": github["id"], "status": "disabled", "notes": "duplicate"},
        headers=headers,
    )
    bindings = client.get(
        f"/usable-emails/{email_one['id']}/platform-bindings",
        headers=headers,
    )
    update = client.put(
        f"/platform-bindings/{github_binding.json()['id']}",
        json={"status": "archived", "notes": "moved to another email"},
        headers=headers,
    )

    assert github_binding.status_code == 201
    assert github_binding.json() == {
        "id": github_binding.json()["id"],
        "usable_email_id": email_one["id"],
        "platform": github,
        "status": "active",
        "notes": "primary login",
    }
    assert stripe_binding.status_code == 201
    assert second_email_github.status_code == 201
    assert duplicate.status_code == 409
    assert bindings.status_code == 200
    assert bindings.json() == {
        "platform_bindings": [
            github_binding.json(),
            stripe_binding.json(),
        ]
    }
    assert update.status_code == 200
    assert update.json()["status"] == "archived"
    assert update.json()["notes"] == "moved to another email"


def test_platform_list_reports_binding_counts(tmp_path):
    client, headers = authenticated_client(tmp_path)
    email_one = client.post(
        "/usable-emails",
        json={"address": "one@example.com", "label": "One"},
        headers=headers,
    ).json()
    email_two = client.post(
        "/usable-emails",
        json={"address": "two@example.com", "label": "Two"},
        headers=headers,
    ).json()
    github = client.post("/platforms", json={"name": "GitHub"}, headers=headers).json()
    stripe = client.post("/platforms", json={"name": "Stripe"}, headers=headers).json()
    client.post(
        f"/usable-emails/{email_one['id']}/platform-bindings",
        json={"platform_id": github["id"], "status": "active", "notes": ""},
        headers=headers,
    )
    client.post(
        f"/usable-emails/{email_two['id']}/platform-bindings",
        json={"platform_id": github["id"], "status": "active", "notes": ""},
        headers=headers,
    )
    client.post(
        f"/usable-emails/{email_two['id']}/platform-bindings",
        json={"platform_id": stripe["id"], "status": "active", "notes": ""},
        headers=headers,
    )

    platforms = client.get("/platforms", headers=headers)

    assert platforms.status_code == 200
    assert platforms.json()["platforms"] == [
        {"id": github["id"], "name": "GitHub", "binding_count": 2},
        {"id": stripe["id"], "name": "Stripe", "binding_count": 1},
    ]


def test_platform_bindings_are_workspace_scoped_and_visible_in_workbench_filters(tmp_path):
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = ApiClient(TestClient(create_app(settings)))

    admin_session = client.post(
        "/auth/login",
        json={"username": "admin", "password": "admin"},
    ).json()
    client.put(
        "/admin/settings/registration",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {admin_session['access_token']}"},
    )
    alice = client.post(
        "/auth/register",
        json={"username": "alice", "password": "alice-pass"},
    ).json()
    bob = client.post(
        "/auth/register",
        json={"username": "bob", "password": "bob-pass"},
    ).json()
    alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
    bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}

    alice_email = client.post(
        "/usable-emails",
        json={"address": "shared@example.com", "label": "Alice"},
        headers=alice_headers,
    ).json()
    alice_unbound = client.post(
        "/usable-emails",
        json={"address": "unbound@example.com", "label": "Alice unbound"},
        headers=alice_headers,
    ).json()
    bob_email = client.post(
        "/usable-emails",
        json={"address": "shared@example.com", "label": "Bob"},
        headers=bob_headers,
    ).json()
    alice_platform = client.post(
        "/platforms", json={"name": "GitHub"}, headers=alice_headers
    ).json()
    bob_platform = client.post("/platforms", json={"name": "GitHub"}, headers=bob_headers).json()

    alice_binding = client.post(
        f"/usable-emails/{alice_email['id']}/platform-bindings",
        json={"platform_id": alice_platform["id"], "status": "active", "notes": ""},
        headers=alice_headers,
    )
    cross_user_binding = client.post(
        f"/usable-emails/{alice_email['id']}/platform-bindings",
        json={"platform_id": bob_platform["id"], "status": "active", "notes": ""},
        headers=bob_headers,
    )
    bob_binding = client.post(
        f"/usable-emails/{bob_email['id']}/platform-bindings",
        json={"platform_id": bob_platform["id"], "status": "active", "notes": ""},
        headers=bob_headers,
    )
    alice_bound = client.get(
        "/workbench/usable-emails",
        params={"platform_binding": "bound"},
        headers=alice_headers,
    )
    alice_unbound_page = client.get(
        "/workbench/usable-emails",
        params={"platform_binding": "unbound"},
        headers=alice_headers,
    )
    bob_bound = client.get(
        "/workbench/usable-emails",
        params={"platform_binding": "bound"},
        headers=bob_headers,
    )

    assert alice_binding.status_code == 201
    assert cross_user_binding.status_code == 404
    assert bob_binding.status_code == 201
    assert alice_bound.json()["usable_emails"] == [
        {
            "id": alice_email["id"],
            "address": "shared@example.com",
            "label": "Alice",
            "kind": "custom",
            "status": "active",
            "group": None,
            "tags": [],
            "platform_binding_count": 1,
        }
    ]
    assert [email["id"] for email in alice_unbound_page.json()["usable_emails"]] == [
        alice_unbound["id"]
    ]
    assert bob_bound.json()["usable_emails"][0]["id"] == bob_email["id"]


def test_platform_candidates_from_messages_do_not_create_platforms_or_bindings(tmp_path):
    client, headers = authenticated_client(tmp_path)
    usable_email = client.post(
        "/usable-emails",
        json={"address": "login@example.com", "label": "Login"},
        headers=headers,
    ).json()

    candidates = client.post(
        "/platform-candidates",
        json={
            "sender": "security@github.com",
            "subject": "GitHub sign-in verification",
            "body": "Use this code to continue signing in.",
        },
        headers=headers,
    )
    platforms = client.get("/platforms", headers=headers)
    bindings = client.get(
        f"/usable-emails/{usable_email['id']}/platform-bindings",
        headers=headers,
    )

    assert candidates.status_code == 200
    assert candidates.json() == {
        "platform_candidates": [{"name": "github.com", "source": "sender"}]
    }
    assert platforms.json() == {"platforms": []}
    assert bindings.json() == {"platform_bindings": []}
