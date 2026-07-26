"""Canonical paths vs deprecated legacy aliases, as declared in the OpenAPI spec."""

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings


def load_spec(tmp_path) -> dict:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    client = TestClient(create_app(settings))
    return client.get("/openapi.json").json()


def test_email_detail_has_plural_canonical_and_deprecated_singular_alias(tmp_path):
    paths = load_spec(tmp_path)["paths"]

    canonical = paths["/api/v1/emails/{email_addr}/{message_id}"]["get"]
    legacy = paths["/api/v1/email/{email_addr}/{message_id}"]["get"]

    assert canonical.get("deprecated") is not True
    assert legacy.get("deprecated") is True


def test_overview_stats_suffix_is_canonical_and_short_forms_deprecated(tmp_path):
    paths = load_spec(tmp_path)["paths"]

    for canonical_path, legacy_path in [
        ("/api/v1/overview/verification-stats", "/api/v1/overview/verification"),
        ("/api/v1/overview/external-api-stats", "/api/v1/overview/external-api"),
        ("/api/v1/overview/pool-stats", "/api/v1/overview/pool"),
    ]:
        assert paths[canonical_path]["get"].get("deprecated") is not True
        assert paths[legacy_path]["get"].get("deprecated") is True


def test_refresh_triggers_are_post_with_deprecated_get_aliases(tmp_path):
    paths = load_spec(tmp_path)["paths"]

    for path in [
        "/api/v1/email-accounts/refresh-all",
        "/api/v1/email-accounts/refresh-failed",
        "/api/v1/email-accounts/trigger-scheduled-refresh",
    ]:
        assert paths[path]["post"].get("deprecated") is not True
        assert paths[path]["get"].get("deprecated") is True
