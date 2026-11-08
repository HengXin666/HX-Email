"""CF Worker multi-upstream: legacy migration, domain routing, per-upstream sync."""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.mail.impl.temp_mail import CFWorkerTempMailProvider, get_temp_mail_options
from hx_email.server.mail.temp_mail import MissingTempMailProviderError
from hx_email.server.settings_service import get_setting, set_setting

API = "/api/v1"
PROVIDER_HTTP = "hx_email.server.mail.impl.temp_mail.cf_provider._http_request"
SYNC_TARGET = "hx_email.api.impl.settings.cf_worker_sync._json_get"
CREATED = json.dumps({"address": "x@b.com", "jwt": "j", "id": 1})


def upstream(upstream_id: str, url: str, domains: list[str], **extra: object) -> dict:
    return {
        "id": upstream_id,
        "name": upstream_id.upper(),
        "base_url": url,
        "admin_key": f"key-{upstream_id}",
        "custom_auth": f"auth-{upstream_id}",
        "enabled": True,
        "domains": domains,
        "excluded_domains": [],
        **extra,
    }


def two_upstreams() -> list[dict]:
    """Two Workers that both serve shared.com; A comes first so it owns it.
    .agents/notes/implemented/feature/2026-11-08-temp-mail-multi-upstream.md
    """
    return [
        upstream("a", "https://a.dev", ["@a.com", "@shared.com"]),
        upstream("b", "https://b.dev", ["@b.com", "@shared.com"]),
    ]


def make_settings(tmp_path, upstreams: list[dict] | None = None) -> Settings:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    if upstreams is not None:
        set_setting(settings, "cf_worker_upstreams", json.dumps(upstreams))
    return settings


def make_client(tmp_path) -> tuple[TestClient, Settings, dict[str, str]]:
    settings = make_settings(tmp_path)
    client = TestClient(create_app(settings))
    session = client.post(
        f"{API}/auth/login", json={"username": "admin", "password": "admin"}
    ).json()
    return client, settings, {"Authorization": f"Bearer {session['access_token']}"}


def test_requested_domain_routes_to_owning_upstream(tmp_path) -> None:
    settings = make_settings(tmp_path, two_upstreams())
    provider = CFWorkerTempMailProvider(settings)

    with patch(PROVIDER_HTTP, return_value=(200, CREATED)) as http:
        mailbox = provider.create_mailbox("me@b.com")

    url, headers = http.call_args[0][1], http.call_args[0][2]
    assert url == "https://b.dev/admin/new_address"
    assert headers["x-admin-auth"] == "key-b"
    assert headers["x-custom-auth"] == "auth-b"
    assert json.loads(mailbox.provider_mailbox_id)["upstream"] == "b"


def test_shared_domain_goes_to_first_upstream_and_default_domain_routes(tmp_path) -> None:
    settings = make_settings(tmp_path, two_upstreams())
    set_setting(settings, "cf_worker_default_domain", "@b.com")
    provider = CFWorkerTempMailProvider(settings)

    with patch(PROVIDER_HTTP, return_value=(200, CREATED)) as http:
        provider.create_mailbox("me@shared.com")
        assert http.call_args[0][1] == "https://a.dev/admin/new_address"
        provider.create_mailbox(None)
        assert http.call_args[0][1] == "https://b.dev/admin/new_address"
        assert http.call_args[0][3]["domain"] == "b.com"


def test_options_union_skips_disabled_and_per_upstream_exclusions(tmp_path) -> None:
    upstreams = two_upstreams()
    upstreams[0]["excluded_domains"] = ["shared.com"]
    upstreams.append(upstream("c", "https://c.dev", ["@c.com"], enabled=False))
    settings = make_settings(tmp_path, upstreams)

    options = get_temp_mail_options(settings, "cf")

    # shared.com is excluded on A but still served by B
    assert options["domains"] == ["@a.com", "@b.com", "@shared.com"]
    provider = CFWorkerTempMailProvider(settings)
    with patch(PROVIDER_HTTP, return_value=(200, CREATED)) as http:
        provider.create_mailbox("me@shared.com")
    assert http.call_args[0][1] == "https://b.dev/admin/new_address"


def test_unknown_domain_with_several_upstreams_is_409(tmp_path) -> None:
    provider = CFWorkerTempMailProvider(make_settings(tmp_path, two_upstreams()))

    with (
        patch(PROVIDER_HTTP) as http,
        pytest.raises(Exception, match=r"nowhere\.com") as excinfo,
    ):
        provider.create_mailbox("me@nowhere.com")

    assert excinfo.value.status_code == 409
    http.assert_not_called()


def test_list_messages_reads_from_stored_upstream(tmp_path) -> None:
    provider = CFWorkerTempMailProvider(make_settings(tmp_path, two_upstreams()))
    mailbox_id = json.dumps({"upstream": "b", "id": "1", "jwt": "jwt-b"})

    with patch(PROVIDER_HTTP, return_value=(200, '{"results": []}')) as http:
        provider.list_messages(mailbox_id)

    url, headers = http.call_args[0][1], http.call_args[0][2]
    assert url.startswith("https://b.dev/api/mails")
    assert headers["Authorization"] == "Bearer jwt-b"
    assert headers["x-custom-auth"] == "auth-b"


def test_legacy_mailbox_without_upstream_reads_default_then_first(tmp_path) -> None:
    upstreams = [upstream("default", "https://legacy.dev", []), *two_upstreams()]
    provider = CFWorkerTempMailProvider(make_settings(tmp_path, upstreams))

    with patch(PROVIDER_HTTP, return_value=(200, '{"results": []}')) as http:
        provider.list_messages(json.dumps({"id": "1", "jwt": "old"}))
        assert http.call_args[0][1].startswith("https://legacy.dev/")
        provider.list_messages("bare-jwt")
        assert http.call_args[0][2]["Authorization"] == "Bearer bare-jwt"

    provider = CFWorkerTempMailProvider(make_settings(tmp_path / "x", two_upstreams()))
    with patch(PROVIDER_HTTP, return_value=(200, '{"results": []}')) as http:
        provider.list_messages(json.dumps({"id": "1", "jwt": "old"}))
    assert http.call_args[0][1].startswith("https://a.dev/")


def test_deleted_upstream_is_missing_and_disabled_upstream_still_reads(tmp_path) -> None:
    upstreams = two_upstreams()
    upstreams[1]["enabled"] = False
    provider = CFWorkerTempMailProvider(make_settings(tmp_path, upstreams))

    with pytest.raises(MissingTempMailProviderError, match="已被删除"):
        provider.list_messages(json.dumps({"upstream": "gone", "jwt": "j"}))
    with patch(PROVIDER_HTTP, return_value=(200, '{"results": []}')) as http:
        provider.list_messages(json.dumps({"upstream": "b", "jwt": "j"}))
    assert http.call_args[0][1].startswith("https://b.dev/")
    with patch(PROVIDER_HTTP) as http, pytest.raises(Exception, match=r"b\.com"):
        provider.create_mailbox("me@b.com")
    http.assert_not_called()


def test_get_settings_exposes_legacy_keys_as_default_upstream(tmp_path) -> None:
    client, settings, headers = make_client(tmp_path)
    set_setting(settings, "cf_worker_base_url", "https://legacy.dev/")
    set_setting(settings, "cf_worker_admin_key", "legacy-key")
    set_setting(settings, "cf_worker_domains", '["@a.com"]')

    fetched = client.get(f"{API}/settings", headers=headers).json()

    [item] = json.loads(fetched["cf_worker_upstreams"])
    assert item["id"] == "default"
    assert item["base_url"] == "https://legacy.dev"
    assert item["admin_key"] == "legacy-key"
    assert item["domains"] == ["@a.com"]


def test_saving_upstreams_encrypts_and_retires_legacy_keys(tmp_path) -> None:
    client, settings, headers = make_client(tmp_path)
    set_setting(settings, "cf_worker_base_url", "https://legacy.dev")
    set_setting(settings, "cf_worker_admin_key", "legacy-key")

    saved = client.put(
        f"{API}/settings",
        json={"cf_worker_upstreams": json.dumps(two_upstreams())},
        headers=headers,
    )

    assert saved.status_code == 200
    assert get_setting(settings, "cf_worker_base_url") == ""
    assert get_setting(settings, "cf_worker_admin_key") == ""
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT value FROM system_settings WHERE key = 'cf_worker_upstreams'"
        ).fetchone()
    assert "key-a" not in str(row["value"])
    fetched = client.get(f"{API}/settings", headers=headers).json()
    assert [item["id"] for item in json.loads(fetched["cf_worker_upstreams"])] == ["a", "b"]


def test_put_rejects_invalid_upstreams(tmp_path) -> None:
    client, _settings, headers = make_client(tmp_path)
    missing_key = upstream("a", "https://a.dev", [], admin_key="")
    invalid_values = (
        "not json",
        '{"id": "a"}',
        json.dumps([upstream("a", "https://a.dev", []), upstream("a", "https://b.dev", [])]),
        json.dumps([missing_key]),
        json.dumps([upstream("", "https://a.dev", [])]),
    )

    for invalid in invalid_values:
        response = client.put(
            f"{API}/settings", json={"cf_worker_upstreams": invalid}, headers=headers
        )
        assert response.status_code == 422, invalid
        assert "cf_worker_upstreams" in response.json()["detail"]
    disabled_blank = json.dumps([upstream("a", "", [], admin_key="", enabled=False)])
    response = client.put(
        f"{API}/settings", json={"cf_worker_upstreams": disabled_blank}, headers=headers
    )
    assert response.status_code == 200


def test_sync_one_upstream_only_touches_that_upstream(tmp_path) -> None:
    client, settings, headers = make_client(tmp_path)
    upstreams = two_upstreams()
    upstreams[1]["excluded_domains"] = ["shared.com", "gone.com"]
    set_setting(settings, "cf_worker_upstreams", json.dumps(upstreams))

    with patch(
        SYNC_TARGET, return_value=(200, '{"domains": ["@b.com", "@shared.com", "@n.com"]}')
    ) as get:
        body = client.post(
            f"{API}/settings/cf-worker-sync-domains", json={"upstream_id": "b"}, headers=headers
        ).json()

    assert body["success"] is True
    assert body["upstream_id"] == "b"
    assert body["excluded_domains"] == ["shared.com"]
    assert get.call_args[0][0] == "https://b.dev/open_api/settings"
    assert get.call_args[0][1]["x-custom-auth"] == "auth-b"
    stored = json.loads(get_setting(settings, "cf_worker_upstreams"))
    assert stored[0]["domains"] == ["@a.com", "@shared.com"]
    assert stored[1]["domains"] == ["@b.com", "@shared.com", "@n.com"]
    assert stored[1]["excluded_domains"] == ["shared.com"]
    assert get_setting(settings, "cf_worker_default_domain") == "@b.com"


def test_sync_unsaved_upstream_returns_domains_without_persisting(tmp_path) -> None:
    client, settings, headers = make_client(tmp_path)
    set_setting(settings, "cf_worker_upstreams", json.dumps(two_upstreams()))

    with patch(SYNC_TARGET, return_value=(200, '{"domains": ["@new.com"]}')) as get:
        body = client.post(
            f"{API}/settings/cf-worker-sync-domains",
            json={"upstream_id": "fresh", "worker_url": "https://fresh.dev/", "custom_auth": "p"},
            headers=headers,
        ).json()

    assert body["success"] is True
    assert body["domains"] == ["@new.com"]
    assert get.call_args[0][0] == "https://fresh.dev/open_api/settings"
    stored = json.loads(get_setting(settings, "cf_worker_upstreams"))
    assert [item["id"] for item in stored] == ["a", "b"]


def test_sync_without_target_syncs_every_enabled_upstream(tmp_path) -> None:
    client, settings, headers = make_client(tmp_path)
    upstreams = two_upstreams()
    upstreams.append(upstream("c", "https://c.dev", [], enabled=False))
    set_setting(settings, "cf_worker_upstreams", json.dumps(upstreams))

    with patch(SYNC_TARGET, return_value=(200, '{"domains": ["@z.com"]}')) as get:
        body = client.post(
            f"{API}/settings/cf-worker-sync-domains", json={}, headers=headers
        ).json()

    assert body["success"] is True
    assert [item["upstream_id"] for item in body["results"]] == ["a", "b"]
    assert get.call_count == 2
