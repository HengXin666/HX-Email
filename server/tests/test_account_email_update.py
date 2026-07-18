from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate

API: str = "/api/v1"


def authenticated_client(tmp_path) -> tuple[TestClient, dict[str, str]]:
    settings: Settings = Settings(data_dir=tmp_path)
    migrate(settings)
    client: TestClient = TestClient(create_app(settings))
    session: dict[str, object] = client.post(
        f"{API}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    ).json()
    headers: dict[str, str] = {"Authorization": f"Bearer {session['access_token']}"}
    return client, headers


def create_account(
    client: TestClient,
    headers: dict[str, str],
    address: str,
    refresh_token: str = "",
) -> dict[str, object]:
    response = client.post(
        f"{API}/email-accounts",
        json={
            "provider": "gmail",
            "primary_address": address,
            "display_name": address,
            "refresh_token": refresh_token,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def test_updating_account_email_updates_primary_usable_email(tmp_path) -> None:
    client, headers = authenticated_client(tmp_path)
    account = create_account(client, headers, "misspelled@gmail.com", "old-refresh-token")

    updated = client.put(
        f"{API}/email-accounts/{account['id']}",
        json={"email": "correct@gmail.com"},
        headers=headers,
    )

    assert updated.status_code == 200
    assert updated.json()["primary_address"] == "correct@gmail.com"
    assert updated.json()["primary_usable_email"]["address"] == "correct@gmail.com"
    assert updated.json()["has_refresh_token"] is False


def test_updating_account_email_rejects_an_existing_address(tmp_path) -> None:
    client, headers = authenticated_client(tmp_path)
    first = create_account(client, headers, "first@gmail.com")
    create_account(client, headers, "existing@gmail.com")

    updated = client.put(
        f"{API}/email-accounts/{first['id']}",
        json={"email": "existing@gmail.com"},
        headers=headers,
    )

    assert updated.status_code == 409
    detail = client.get(f"{API}/email-accounts/{first['id']}", headers=headers).json()
    assert detail["primary_address"] == "first@gmail.com"
    assert detail["primary_usable_email"]["address"] == "first@gmail.com"
