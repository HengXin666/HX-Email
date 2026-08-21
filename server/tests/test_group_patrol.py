"""Group token patrol: index counts, ungrouped bucket, channel restriction,
and group-scoped refresh (SSE + external API)."""

from pathlib import Path

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.mail.email_accounts import add_email_account
from hx_email.server.mail.impl.patrol.index import get_group_token_index
from hx_email.server.mail.impl.patrol.refresh import refresh_group_accounts_sync
from hx_email.server.workspace.groups import create_group


def make_settings(tmp_path: Path) -> Settings:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    return settings


def add_gmail_account(settings: Settings, user_id: int, email: str, group_id: int | None) -> None:
    add_email_account(
        settings,
        user_id,
        "gmail",
        email,
        email,
        imap_host="imap.gmail.com",
        imap_port=993,
        client_id="cid",
        refresh_token="rt",
        group_id=group_id,
    )


def test_group_token_index_counts_accounts_and_valid_tokens(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    group = create_group(settings, 1, "gmail 号", "#3fb950", allowed_provider="gmail")
    add_gmail_account(settings, 1, "a@gmail.com", group.id)
    add_gmail_account(settings, 1, "b@gmail.com", group.id)
    add_gmail_account(settings, 1, "c@gmail.com", None)  # 未分组

    index = get_group_token_index(settings, 1)

    assert index.groups[0].bucket.account_count == 2
    assert index.groups[0].bucket.oauth_account_count == 2
    assert index.groups[0].bucket.valid_token_count == 0
    assert index.ungrouped.account_count == 1

    # 模拟一次成功的 token 刷新: last_refresh_at 有值, refresh_failed_at 为 NULL
    with connect(settings) as connection:
        connection.execute(
            "UPDATE email_accounts SET last_refresh_at = ?, refresh_failed_at = NULL"
            " WHERE user_id = ? AND primary_address = ?",
            ("2026-01-01T00:00:00Z", 1, "a@gmail.com"),
        )

    index = get_group_token_index(settings, 1)
    assert index.groups[0].bucket.valid_token_count == 1
    assert index.groups[0].bucket.invalid_token_count == 0

    # 模拟失败: refresh_failed_at 有值
    with connect(settings) as connection:
        connection.execute(
            "UPDATE email_accounts SET refresh_failed_at = ? WHERE user_id = ?"
            " AND primary_address = ?",
            ("2026-01-01T00:00:00Z", 1, "b@gmail.com"),
        )

    index = get_group_token_index(settings, 1)
    assert index.groups[0].bucket.valid_token_count == 1
    assert index.groups[0].bucket.invalid_token_count == 1


def test_group_token_index_ignores_other_users(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    group = create_group(settings, 1, "gmail 号", "#3fb950")
    add_gmail_account(settings, 1, "a@gmail.com", group.id)
    add_gmail_account(settings, 2, "other@gmail.com", None)

    index = get_group_token_index(settings, 1)
    assert index.groups[0].bucket.account_count == 1
    assert index.ungrouped.account_count == 0


def test_ungrouped_bucket_only_counts_unassigned(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    group = create_group(settings, 1, "gmail 号", "#3fb950")
    add_gmail_account(settings, 1, "a@gmail.com", group.id)
    add_gmail_account(settings, 1, "b@gmail.com", None)
    add_gmail_account(settings, 1, "c@gmail.com", None)

    index = get_group_token_index(settings, 1)
    assert index.groups[0].bucket.account_count == 1
    assert index.ungrouped.account_count == 2


def test_add_account_to_channel_restricted_group_raises(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    group = create_group(settings, 1, "gmail 号", "#3fb950", allowed_provider="gmail")

    try:
        add_email_account(
            settings,
            1,
            "outlook",
            "x@outlook.com",
            "x",
            client_id="cid",
            refresh_token="rt",
            group_id=group.id,
        )
        raise AssertionError("outlook account must be rejected by gmail-only group")
    except ValueError as error:
        assert "outlook" in str(error)
        assert "channel restricted" in str(error)


def test_add_account_to_unrestricted_group_allowed(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    group = create_group(settings, 1, "通用", "#58a6ff")
    add_gmail_account(settings, 1, "a@gmail.com", group.id)
    add_email_account(
        settings,
        1,
        "outlook",
        "x@outlook.com",
        "x",
        client_id="cid",
        refresh_token="rt",
        group_id=group.id,
    )
    index = get_group_token_index(settings, 1)
    assert index.groups[0].bucket.account_count == 2


def test_group_route_enforces_channel_restriction_on_update(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    client = TestClient(create_app(settings))
    client.__enter__()
    session = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin"},
    ).json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    group = client.post(
        "/api/v1/groups",
        json={"name": "gmail 号", "color": "#3fb950", "allowed_provider": "gmail"},
        headers=headers,
    ).json()
    account = client.post(
        "/api/v1/email-accounts",
        json={
            "provider": "outlook",
            "primary_address": "x@outlook.com",
            "display_name": "x",
            "client_id": "cid",
            "refresh_token": "rt",
        },
        headers=headers,
    ).json()

    response = client.put(
        f"/api/v1/email-accounts/{account['id']}",
        json={"group_id": group["id"]},
        headers=headers,
    )
    assert response.status_code == 422
    assert "channel restricted" in response.json()["detail"]


def test_group_refresh_sync_returns_summary_and_results(tmp_path: Path, monkeypatch) -> None:
    settings = make_settings(tmp_path)
    group = create_group(settings, 1, "gmail 号", "#3fb950")
    add_gmail_account(settings, 1, "a@gmail.com", group.id)
    add_gmail_account(settings, 1, "b@gmail.com", group.id)

    import hx_email.server.mail.impl.patrol.refresh as patrol_refresh

    def fake_refresh(*args, **kwargs) -> dict[str, object]:
        return {"success": True, "message": "mocked", "error_detail": ""}

    monkeypatch.setattr(patrol_refresh, "try_refresh_provider_oauth_token", fake_refresh)

    result = refresh_group_accounts_sync(settings, 1, group.id)
    assert result["summary"]["total"] == 2
    assert result["summary"]["success"] == 2
    assert result["summary"]["failed"] == 0
    assert len(result["results"]) == 2


def test_group_refresh_sync_skips_non_oauth_accounts(tmp_path: Path, monkeypatch) -> None:
    settings = make_settings(tmp_path)
    group = create_group(settings, 1, "通用", "#58a6ff")
    add_email_account(settings, 1, "qq", "x@qq.com", "x", group_id=group.id)

    result = refresh_group_accounts_sync(settings, 1, group.id)
    assert result["summary"]["total"] == 0


def test_ungrouped_refresh_only_touches_unassigned(tmp_path: Path, monkeypatch) -> None:
    settings = make_settings(tmp_path)
    group = create_group(settings, 1, "gmail 号", "#3fb950")
    add_gmail_account(settings, 1, "a@gmail.com", group.id)
    add_gmail_account(settings, 1, "b@gmail.com", None)

    import hx_email.server.mail.impl.patrol.refresh as patrol_refresh

    def fake_refresh(*args, **kwargs) -> dict[str, object]:
        return {"success": True, "message": "mocked", "error_detail": ""}

    monkeypatch.setattr(patrol_refresh, "try_refresh_provider_oauth_token", fake_refresh)

    group_result = refresh_group_accounts_sync(settings, 1, group.id)
    ungrouped_result = refresh_group_accounts_sync(settings, 1, 0)
    assert group_result["summary"]["total"] == 1
    assert ungrouped_result["summary"]["total"] == 1


def test_external_token_status_endpoint(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    from hx_email.server.settings_service import set_setting

    set_setting(settings, "external_api_key", "patrol-key")
    group = create_group(settings, 1, "gmail 号", "#3fb950", allowed_provider="gmail")
    add_gmail_account(settings, 1, "a@gmail.com", group.id)

    with TestClient(create_app(settings)) as client:
        response = client.get(
            "/api/external/token-status",
            params={"user_id": 1},
            headers={"Authorization": "Bearer patrol-key"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    groups = body["data"]["groups"]
    assert groups[0]["group_id"] == group.id
    assert groups[0]["allowed_provider"] == "gmail"
    assert groups[0]["account_count"] == 1


def test_external_token_status_requires_api_key(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/external/token-status")
    assert response.status_code == 401


def test_external_token_refresh_endpoint(tmp_path: Path, monkeypatch) -> None:
    settings = make_settings(tmp_path)
    from hx_email.server.settings_service import set_setting

    set_setting(settings, "external_api_key", "patrol-key")
    group = create_group(settings, 1, "gmail 号", "#3fb950")
    add_gmail_account(settings, 1, "a@gmail.com", group.id)

    import hx_email.server.mail.impl.patrol.refresh as patrol_refresh

    def fake_refresh(*args, **kwargs) -> dict[str, object]:
        return {"success": True, "message": "mocked", "error_detail": ""}

    monkeypatch.setattr(patrol_refresh, "try_refresh_provider_oauth_token", fake_refresh)

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/external/token/refresh",
            json={"group_id": group.id},
            headers={"Authorization": "Bearer patrol-key"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["summary"]["total"] == 1


def test_groups_endpoint_includes_token_counts(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    client = TestClient(create_app(settings))
    client.__enter__()
    session = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin"},
    ).json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    group = client.post(
        "/api/v1/groups",
        json={"name": "gmail 号", "color": "#3fb950", "allowed_provider": "gmail"},
        headers=headers,
    ).json()
    add_gmail_account(settings, 1, "a@gmail.com", group["id"])

    response = client.get("/api/v1/groups", headers=headers)
    groups = response.json()
    target = next(g for g in groups if g["id"] == group["id"])
    assert target["allowed_provider"] == "gmail"
    assert target["account_count"] == 1
    assert target["valid_token_count"] == 0
