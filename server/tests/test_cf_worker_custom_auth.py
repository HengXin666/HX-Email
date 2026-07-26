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


def test_sync_domains_uses_open_api_and_sends_custom_auth(tmp_path) -> None:
    client, _settings, headers = make_client(tmp_path)
    client.put(
        f"{API}/settings",
        json={
            "cf_worker_base_url": "https://worker.example.workers.dev",
            "cf_worker_custom_auth": "custom-pass",
        },
        headers=headers,
    )

    with patch(
        "hx_email.api.impl.settings.cf_worker_sync._json_get",
        return_value=(200, '{"domains": ["@a.com", "@b.com"], "defaultDomains": ["@a.com"]}'),
    ) as json_get:
        response = client.post(f"{API}/settings/cf-worker-sync-domains", json={}, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["domains"] == ["@a.com", "@b.com"]
    assert body["default_domain"] == "@a.com"
    assert body["message"]
    url, sent_headers = json_get.call_args[0][0], json_get.call_args[0][1]
    assert url == "https://worker.example.workers.dev/open_api/settings"
    assert sent_headers["x-custom-auth"] == "custom-pass"
    # Cloudflare bot protection (error 1010) blocks the default urllib UA
    assert sent_headers["User-Agent"].startswith("Mozilla/5.0")


def test_sync_domains_persists_domains_and_default_domain(tmp_path) -> None:
    client, _settings, headers = make_client(tmp_path)

    with patch(
        "hx_email.api.impl.settings.cf_worker_sync._json_get",
        return_value=(200, '{"domains": ["@a.com", "@b.com"], "defaultDomains": ["@b.com"]}'),
    ):
        client.post(
            f"{API}/settings/cf-worker-sync-domains",
            json={"worker_url": "https://w.example.dev"},
            headers=headers,
        )

    fetched = client.get(f"{API}/settings", headers=headers).json()
    assert fetched["cf_worker_domains"] == '["@a.com", "@b.com"]'
    assert fetched["cf_worker_default_domain"] == "@b.com"


def test_sync_domains_payload_overrides_stored_custom_auth(tmp_path) -> None:
    client, _settings, headers = make_client(tmp_path)

    with patch(
        "hx_email.api.impl.settings.cf_worker_sync._json_get",
        return_value=(200, '{"domains": ["@a.com"]}'),
    ) as json_get:
        client.post(
            f"{API}/settings/cf-worker-sync-domains",
            json={
                "worker_url": "https://w.example.dev",
                "custom_auth": "unsaved-pass",
            },
            headers=headers,
        )

    sent_headers = json_get.call_args[0][1]
    assert sent_headers["x-custom-auth"] == "unsaved-pass"


def test_sync_domains_omits_custom_auth_header_when_unset(tmp_path) -> None:
    client, _settings, headers = make_client(tmp_path)

    with patch(
        "hx_email.api.impl.settings.cf_worker_sync._json_get",
        return_value=(200, '{"domains": ["@a.com"]}'),
    ) as json_get:
        client.post(
            f"{API}/settings/cf-worker-sync-domains",
            json={"worker_url": "https://w.example.dev"},
            headers=headers,
        )

    sent_headers = json_get.call_args[0][1]
    assert "x-custom-auth" not in sent_headers


def test_sync_domains_reports_http_error_with_message(tmp_path) -> None:
    client, _settings, headers = make_client(tmp_path)

    with patch(
        "hx_email.api.impl.settings.cf_worker_sync._json_get",
        return_value=(401, '{"error": "unauthorized"}'),
    ):
        response = client.post(
            f"{API}/settings/cf-worker-sync-domains",
            json={"worker_url": "https://w.example.dev"},
            headers=headers,
        )

    body = response.json()
    assert body["success"] is False
    assert "HTTP 401" in body["message"]


def test_sync_domains_reports_empty_domains_with_message(tmp_path) -> None:
    client, _settings, headers = make_client(tmp_path)

    with patch(
        "hx_email.api.impl.settings.cf_worker_sync._json_get",
        return_value=(200, '{"domains": []}'),
    ):
        response = client.post(
            f"{API}/settings/cf-worker-sync-domains",
            json={"worker_url": "https://w.example.dev"},
            headers=headers,
        )

    body = response.json()
    assert body["success"] is False
    assert body["message"]


def test_sync_domains_reports_non_json_with_message(tmp_path) -> None:
    client, _settings, headers = make_client(tmp_path)

    with patch(
        "hx_email.api.impl.settings.cf_worker_sync._json_get",
        return_value=(200, "<html>not json</html>"),
    ):
        response = client.post(
            f"{API}/settings/cf-worker-sync-domains",
            json={"worker_url": "https://w.example.dev"},
            headers=headers,
        )

    body = response.json()
    assert body["success"] is False
    assert body["message"]
