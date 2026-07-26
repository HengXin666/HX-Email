"""CF Worker PASSWORDS (custom auth): settings storage and x-custom-auth header."""

from unittest.mock import patch

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import connect, migrate

API = "/api/v1"


def login_admin(client: TestClient, settings: Settings) -> dict[str, str]:
    session = client.post(
        f"{API}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    ).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def make_client(tmp_path):
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    return client, settings, login_admin(client, settings)


def test_custom_auth_round_trips_and_is_encrypted_at_rest(tmp_path) -> None:
    client, settings, headers = make_client(tmp_path)

    client.put(
        f"{API}/settings",
        json={"cf_worker_custom_auth": "secret-pass-1"},
        headers=headers,
    )

    fetched = client.get(f"{API}/settings", headers=headers).json()
    assert fetched["cf_worker_custom_auth"] == "secret-pass-1"
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT value FROM system_settings WHERE key = 'cf_worker_custom_auth'"
        ).fetchone()
    assert row is not None
    assert "secret-pass-1" not in str(row["value"])


def test_sync_domains_sends_custom_auth_and_admin_headers(tmp_path) -> None:
    client, _settings, headers = make_client(tmp_path)
    client.put(
        f"{API}/settings",
        json={
            "cf_worker_base_url": "https://worker.example.workers.dev",
            "cf_worker_admin_key": "admin-key",
            "cf_worker_custom_auth": "custom-pass",
        },
        headers=headers,
    )

    with patch(
        "hx_email.api.impl.settings.settings_test_routes._json_get",
        return_value=(200, '{"domains": ["@a.com", "@b.com"]}'),
    ) as json_get:
        response = client.post(f"{API}/settings/cf-worker-sync-domains", json={}, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"success": True, "domains": ["@a.com", "@b.com"]}
    url, sent_headers = json_get.call_args[0][0], json_get.call_args[0][1]
    assert url == "https://worker.example.workers.dev/admin/domains"
    assert sent_headers["Authorization"] == "Bearer admin-key"
    assert sent_headers["x-custom-auth"] == "custom-pass"


def test_sync_domains_payload_overrides_stored_custom_auth(tmp_path) -> None:
    client, _settings, headers = make_client(tmp_path)

    with patch(
        "hx_email.api.impl.settings.settings_test_routes._json_get",
        return_value=(200, '{"domains": []}'),
    ) as json_get:
        client.post(
            f"{API}/settings/cf-worker-sync-domains",
            json={
                "worker_url": "https://w.example.dev",
                "admin_key": "k",
                "custom_auth": "unsaved-pass",
            },
            headers=headers,
        )

    sent_headers = json_get.call_args[0][1]
    assert sent_headers["x-custom-auth"] == "unsaved-pass"


def test_sync_domains_omits_custom_auth_header_when_unset(tmp_path) -> None:
    client, _settings, headers = make_client(tmp_path)

    with patch(
        "hx_email.api.impl.settings.settings_test_routes._json_get",
        return_value=(200, '{"domains": []}'),
    ) as json_get:
        client.post(
            f"{API}/settings/cf-worker-sync-domains",
            json={"worker_url": "https://w.example.dev"},
            headers=headers,
        )

    sent_headers = json_get.call_args[0][1]
    assert "x-custom-auth" not in sent_headers
