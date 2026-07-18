from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.security import decrypt_secret

API = "/api/v1"


def login_admin(client: TestClient, settings: Settings) -> dict[str, str]:
    session = client.post(
        f"{API}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    ).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def create_gmail_account(client: TestClient, headers: dict[str, str]) -> int:
    response = client.post(
        f"{API}/email-accounts",
        json={
            "provider": "gmail",
            "primary_address": "owner@gmail.com",
            "display_name": "Owner",
            "imap_password": "old-app-password",
        },
        headers=headers,
    )
    return int(response.json()["id"])


def test_google_oauth_config_and_prepare_keep_secret_private(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)
    account_id = create_gmail_account(client, headers)

    saved = client.put(
        f"{API}/google-oauth/config",
        json={
            "client_id": "google-client-id",
            "client_secret": "google-client-secret",
            "redirect_uri": "http://localhost:8000/api/v1/google-oauth/callback",
        },
        headers=headers,
    )
    prepared = client.post(
        f"{API}/email-accounts/{account_id}/google-oauth/prepare", headers=headers
    )

    assert saved.status_code == 200
    assert saved.json() == {
        "client_id": "google-client-id",
        "redirect_uri": "http://localhost:8000/api/v1/google-oauth/callback",
        "has_client_secret": True,
    }
    assert "google-client-secret" not in saved.text
    assert prepared.status_code == 200
    params = parse_qs(urlparse(prepared.json()["authorization_url"]).query)
    assert params["client_id"] == ["google-client-id"]
    assert params["access_type"] == ["offline"]
    assert params["prompt"] == ["consent"]
    assert "https://mail.google.com/" in params["scope"][0]


def test_google_oauth_callback_saves_matching_account_credentials(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)
    account_id = create_gmail_account(client, headers)
    client.put(
        f"{API}/google-oauth/config",
        json={
            "client_id": "google-client-id",
            "client_secret": "google-client-secret",
            "redirect_uri": "http://localhost:8000/api/v1/google-oauth/callback",
        },
        headers=headers,
    )
    prepared = client.post(
        f"{API}/email-accounts/{account_id}/google-oauth/prepare", headers=headers
    ).json()

    with (
        patch(
            "hx_email.server.mail.google_oauth.impl.flow.exchange_google_code",
            return_value={"access_token": "access-token", "refresh_token": "refresh-token"},
        ),
        patch(
            "hx_email.server.mail.google_oauth.impl.flow.fetch_google_email",
            return_value="owner@gmail.com",
        ),
    ):
        callback = client.get(
            f"{API}/google-oauth/callback",
            params={"code": "auth-code", "state": prepared["state"]},
        )

    with connect(settings) as connection:
        row = connection.execute(
            "SELECT client_id, refresh_token, imap_password FROM email_accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
    assert callback.status_code == 200
    assert "授权成功" in callback.text
    assert row is not None
    assert row["client_id"] == "google-client-id"
    assert row["imap_password"] == ""
    assert str(row["refresh_token"]).startswith("enc:v1:")
    assert decrypt_secret(settings, str(row["refresh_token"])) == "refresh-token"
    detail = client.get(f"{API}/email-accounts/{account_id}", headers=headers).json()
    assert detail["refresh_token"] == ""
    assert detail["has_refresh_token"] is True


def test_gmail_refresh_route_uses_google_refresh_endpoint(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)
    account_id = create_gmail_account(client, headers)
    client.put(
        f"{API}/email-accounts/{account_id}",
        json={"client_id": "google-client-id", "refresh_token": "refresh-token"},
        headers=headers,
    )

    with patch(
        "hx_email.server.mail.impl.oauth_tool.refresh_google_token",
        return_value={"success": True, "message": "ok", "error_detail": ""},
    ) as google_refresh:
        refreshed = client.post(f"{API}/email-accounts/{account_id}/refresh", headers=headers)

    assert refreshed.status_code == 200
    google_refresh.assert_called_once()


def test_google_oauth_rejects_a_different_google_account(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)
    account_id = create_gmail_account(client, headers)
    client.put(
        f"{API}/google-oauth/config",
        json={
            "client_id": "google-client-id",
            "client_secret": "google-client-secret",
            "redirect_uri": "http://localhost:8000/api/v1/google-oauth/callback",
        },
        headers=headers,
    )
    prepared = client.post(
        f"{API}/email-accounts/{account_id}/google-oauth/prepare", headers=headers
    ).json()

    with (
        patch(
            "hx_email.server.mail.google_oauth.impl.flow.exchange_google_code",
            return_value={"access_token": "access-token", "refresh_token": "refresh-token"},
        ),
        patch(
            "hx_email.server.mail.google_oauth.impl.flow.fetch_google_email",
            return_value="attacker@gmail.com",
        ),
    ):
        callback = client.get(
            f"{API}/google-oauth/callback",
            params={"code": "auth-code", "state": prepared["state"]},
        )

    with connect(settings) as connection:
        row = connection.execute(
            "SELECT client_id, refresh_token, imap_password FROM email_accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
    assert callback.status_code == 400
    assert "does not match" in callback.text
    assert row is not None
    assert dict(row) == {
        "client_id": "",
        "refresh_token": "",
        "imap_password": "old-app-password",
    }
