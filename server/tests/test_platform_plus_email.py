from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate

API = "/api/v1"


def login_admin(client: TestClient, settings: Settings) -> dict[str, str]:
    session = client.post(
        f"{API}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    ).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def test_plus_subaddress_can_be_standalone_usable_email_bound_to_platform(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)

    usable_email = client.post(
        f"{API}/usable-emails",
        json={"address": "owner+github@example.com", "label": "GitHub alias"},
        headers=headers,
    )
    platform = client.post(f"{API}/platforms", json={"name": "GitHub"}, headers=headers)
    binding = client.post(
        f"{API}/usable-emails/{usable_email.json()['id']}/platform-bindings",
        json={"platform_id": platform.json()["id"], "status": "active", "notes": "plus"},
        headers=headers,
    )

    assert usable_email.status_code == 201
    assert usable_email.json()["kind"] == "custom"
    assert binding.status_code == 201
    assert binding.json()["usable_email_id"] == usable_email.json()["id"]
    assert binding.json()["platform"] == platform.json()
