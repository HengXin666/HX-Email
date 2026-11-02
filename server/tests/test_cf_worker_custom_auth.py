"""CF Worker PASSWORDS (custom auth): settings storage and x-custom-auth header."""

from unittest.mock import patch

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.settings_service import set_setting

API = "/api/v1"
SYNC_TARGET = "hx_email.api.impl.settings.cf_worker_sync._json_get"
PROVIDER_HTTP = "hx_email.server.mail.impl.temp_mail.cf_provider._http_request"


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


def test_sync_domains_prunes_stale_excluded_domains(tmp_path) -> None:
    client, _settings, headers = make_client(tmp_path)
    saved = client.put(
        f"{API}/settings",
        json={"cf_worker_excluded_domains": '["@b.com", "gone.com"]'},
        headers=headers,
    )
    assert saved.status_code == 200

    with patch(
        "hx_email.api.impl.settings.cf_worker_sync._json_get",
        return_value=(200, '{"domains": ["@a.com", "@b.com"]}'),
    ):
        response = client.post(
            f"{API}/settings/cf-worker-sync-domains",
            json={"worker_url": "https://w.example.dev"},
            headers=headers,
        )

    body = response.json()
    assert body["success"] is True
    assert body["excluded_domains"] == ["b.com"]
    fetched = client.get(f"{API}/settings", headers=headers).json()
    assert fetched["cf_worker_excluded_domains"] == '["b.com"]'


def test_put_settings_rejects_invalid_excluded_domains(tmp_path) -> None:
    client, _settings, headers = make_client(tmp_path)

    for invalid in ("not json", '{"a.com": true}', '["a.com", 1]'):
        response = client.put(
            f"{API}/settings",
            json={"cf_worker_excluded_domains": invalid},
            headers=headers,
        )
        assert response.status_code == 422
        assert "cf_worker_excluded_domains" in response.json()["detail"]


def sync_domains(client: TestClient, headers: dict[str, str], domains_json: str) -> dict:
    with patch(SYNC_TARGET, return_value=(200, f'{{"domains": {domains_json}}}')):
        response = client.post(
            f"{API}/settings/cf-worker-sync-domains",
            json={"worker_url": "https://w.example.dev"},
            headers=headers,
        )
    return response.json()


def configure_cf_worker(client: TestClient, headers: dict[str, str], excluded: str) -> None:
    saved = client.put(
        f"{API}/settings",
        json={
            "cf_worker_base_url": "https://worker.example.dev",
            "cf_worker_admin_key": "admin-key",
            "cf_worker_domains": '["@a.com", "@b.com"]',
            "cf_worker_excluded_domains": excluded,
        },
        headers=headers,
    )
    assert saved.status_code == 200


def test_put_settings_cleans_and_dedupes_excluded_domains(tmp_path) -> None:
    client, _settings, headers = make_client(tmp_path)

    saved = client.put(
        f"{API}/settings",
        json={
            "cf_worker_excluded_domains": (
                '["", "   ", "@", "@@", " A.com ", "@a.com", "b.com", "@@B.COM"]'
            )
        },
        headers=headers,
    )

    assert saved.status_code == 200
    fetched = client.get(f"{API}/settings", headers=headers).json()
    assert fetched["cf_worker_excluded_domains"] == '["a.com", "b.com"]'


def test_sync_prune_keeps_excluded_domain_that_differs_only_in_case(tmp_path) -> None:
    client, _settings, headers = make_client(tmp_path)
    set_setting(_settings, "cf_worker_excluded_domains", '["A.com", "gone.com"]')

    body = sync_domains(client, headers, '["@a.com", "@b.com"]')

    assert body["success"] is True
    assert body["excluded_domains"] == ["a.com"]
    fetched = client.get(f"{API}/settings", headers=headers).json()
    assert fetched["cf_worker_excluded_domains"] == '["a.com"]'


def test_sync_prune_writes_back_clean_deduplicated_form(tmp_path) -> None:
    client, settings, headers = make_client(tmp_path)
    set_setting(settings, "cf_worker_excluded_domains", '["@a.com", "a.com", "", "@", "@A.COM"]')

    body = sync_domains(client, headers, '["@a.com", "@b.com"]')

    assert body["excluded_domains"] == ["a.com"]
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT value FROM system_settings WHERE key = 'cf_worker_excluded_domains'"
        ).fetchone()
    assert row["value"] == '["a.com"]'


def test_create_mailbox_returns_409_when_all_domains_excluded(tmp_path) -> None:
    client, _settings, headers = make_client(tmp_path)
    configure_cf_worker(client, headers, '["a.com", "B.com"]')

    with patch(PROVIDER_HTTP) as http:
        response = client.post(f"{API}/temp-mail/cf/mailboxes", json={}, headers=headers)

    assert response.status_code == 409
    assert "已被删除" in response.json()["detail"]
    http.assert_not_called()


def test_create_mailbox_returns_409_for_explicit_excluded_address(tmp_path) -> None:
    client, _settings, headers = make_client(tmp_path)
    configure_cf_worker(client, headers, '["a.com"]')

    created = '{"address": "me@a.com", "jwt": "j", "id": 1}'
    with patch(PROVIDER_HTTP, return_value=(200, created)) as http:
        response = client.post(
            f"{API}/temp-mail/cf/mailboxes", json={"address": "me@A.com"}, headers=headers
        )

    assert response.status_code == 409
    assert "a.com" in response.json()["detail"]
    assert "被删除" in response.json()["detail"]
    http.assert_not_called()
