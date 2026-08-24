from __future__ import annotations

from unittest.mock import Mock, patch

from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.security import decrypt_secret
from hx_email.server.mail.impl.oauth_tool import (
    try_refresh_oauth_token,
    try_refresh_provider_oauth_token,
)
from hx_email.server.mail.impl.refresh.single import refresh_single_account
from hx_email.server.mail.impl.refresh_service import (
    refresh_selected_accounts,
)
from hx_email.server.mail.verification import EmptyMailboxProvider


def test_try_refresh_oauth_token_uses_proxy() -> None:
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"access_token": "access", "refresh_token": "new-refresh"}
    proxy_url = "http://127.0.0.1:2334"

    with patch("hx_email.server.mail.impl.oauth_tool.requests.post", return_value=response) as post:
        result = try_refresh_oauth_token("cid", "rt", proxy_url=proxy_url)

    assert result["success"] is True
    assert post.call_args.kwargs["proxies"] == {"http": proxy_url, "https": proxy_url}


def test_refresh_single_account_passes_group_proxy_to_token_refresh(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    _insert_proxy_account(settings)

    with patch(
        "hx_email.server.mail.impl.refresh.single.try_refresh_provider_oauth_token",
        return_value={"success": True, "message": "ok", "error_detail": ""},
    ) as refresh:
        result = refresh_single_account(settings, 1, 1, EmptyMailboxProvider())

    assert result["success"] is True
    assert refresh.call_args.args[4] == "http://127.0.0.1:2334"


def test_refresh_single_account_persists_rotated_microsoft_refresh_token(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    _insert_proxy_account(settings)

    with patch(
        "hx_email.server.mail.impl.oauth_tool.try_refresh_oauth_token",
        return_value={
            "success": True,
            "message": "ok",
            "error_detail": "",
            "refresh_token": "rotated-refresh-token",
        },
    ):
        result = refresh_single_account(settings, 1, 1, EmptyMailboxProvider())

    with connect(settings) as connection:
        stored: str = str(
            connection.execute("SELECT refresh_token FROM email_accounts WHERE id = 1").fetchone()[
                "refresh_token"
            ]
        )
    assert result["success"] is True
    assert stored.startswith("enc:v1:")
    assert decrypt_secret(settings, stored) == "rotated-refresh-token"


def test_refresh_selected_accounts_passes_group_proxy_to_token_refresh(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    _insert_proxy_account(settings)

    with patch(
        "hx_email.server.mail.impl.refresh_service.try_refresh_provider_oauth_token",
        return_value={"success": True, "message": "ok", "error_detail": ""},
    ) as refresh:
        events = list(refresh_selected_accounts(settings, 1, [1], EmptyMailboxProvider()))

    assert any("progress" in event for event in events)
    assert refresh.call_args.kwargs["proxy_url"] == "http://127.0.0.1:2334"


def test_refresh_selected_accounts_skips_password_provider(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    _insert_proxy_account(settings)
    with connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO email_accounts
                (id, user_id, provider, primary_address, status, client_id,
                 refresh_token)
            VALUES (2, 1, '163', 'password@example.com', 'active', '', 'app-password')
            """
        )

    with patch(
        "hx_email.server.mail.impl.refresh_service.try_refresh_provider_oauth_token",
        return_value={"success": True, "message": "ok", "error_detail": ""},
    ) as refresh:
        events = list(refresh_selected_accounts(settings, 1, [1, 2], EmptyMailboxProvider()))

    assert refresh.call_count == 1
    assert '"total": 1' in events[0]


def test_google_refresh_persists_rotated_refresh_token(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    with connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO email_accounts
                (id, user_id, provider, primary_address, status, client_id,
                 refresh_token)
            VALUES (1, 1, 'gmail', 'owner@gmail.com', 'active', 'google-client', 'old-token')
            """
        )

    with patch(
        "hx_email.server.mail.impl.oauth_tool.refresh_google_token",
        return_value={
            "success": True,
            "message": "ok",
            "error_detail": "",
            "refresh_token": "rotated-google-token",
        },
    ):
        result = try_refresh_provider_oauth_token(
            settings, "gmail", "google-client", "old-token", account_id=1
        )

    with connect(settings) as connection:
        stored = str(connection.execute("SELECT refresh_token FROM email_accounts").fetchone()[0])
    assert result["success"] is True
    assert decrypt_secret(settings, stored) == "rotated-google-token"


def _read_account_times(settings: Settings, account_id: int) -> dict[str, object]:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT last_refresh_at, refresh_failed_at FROM email_accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
    assert row is not None
    return {
        "last_refresh_at": row["last_refresh_at"],
        "refresh_failed_at": row["refresh_failed_at"],
    }


def test_refresh_failure_records_first_success_to_failure_transition(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    _insert_proxy_account(settings)

    fail_result = {"success": False, "message": "boom", "error_detail": "invalid_grant"}
    with patch(
        "hx_email.server.mail.impl.refresh.single.try_refresh_provider_oauth_token",
        return_value=fail_result,
    ):
        first = refresh_single_account(settings, 1, 1, EmptyMailboxProvider())
        first_times = _read_account_times(settings, 1)
        # 连续失败: 保留首次从成功转入失败的时间, 不覆盖
        refresh_single_account(settings, 1, 1, EmptyMailboxProvider())
        second_times = _read_account_times(settings, 1)

    assert first["success"] is False
    assert first_times["refresh_failed_at"] is not None
    assert first_times["last_refresh_at"] is None
    assert second_times["refresh_failed_at"] == first_times["refresh_failed_at"]

    with patch(
        "hx_email.server.mail.impl.refresh.single.try_refresh_provider_oauth_token",
        return_value={"success": True, "message": "ok", "error_detail": ""},
    ):
        refresh_single_account(settings, 1, 1, EmptyMailboxProvider())
        recovered_times = _read_account_times(settings, 1)

    # 成功后清除失败转移时间, 并记录最近刷新凭证时间
    assert recovered_times["refresh_failed_at"] is None
    assert recovered_times["last_refresh_at"] is not None


def _insert_proxy_account(settings: Settings) -> None:
    with connect(settings) as conn:
        conn.execute(
            """
            INSERT INTO groups (id, user_id, name, color, proxy_url)
            VALUES (10, 1, 'Proxy', '#58a6ff', 'http://127.0.0.1:2334')
            """
        )
        conn.execute(
            """
            INSERT INTO email_accounts
                (id, user_id, provider, primary_address, status, client_id,
                 refresh_token, group_id)
            VALUES (1, 1, 'outlook', 'owner@example.com', 'active', 'cid', 'rt', 10)
            """
        )


def test_refresh_is_scoped_to_owning_user(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
    _insert_proxy_account(settings)  # 属于 user_id=1

    with patch(
        "hx_email.server.mail.impl.refresh_service.try_refresh_provider_oauth_token",
        return_value={"success": True, "message": "ok", "error_detail": ""},
    ) as refresh:
        # 其他用户 (user_id=2) 不能刷新/探测 user 1 的账户
        cross_result = refresh_single_account(settings, 2, 1, EmptyMailboxProvider())
        cross_events = list(refresh_selected_accounts(settings, 2, [1], EmptyMailboxProvider()))

    assert cross_result["success"] is False
    assert cross_result["message"] == "Account not found"
    assert "email" not in cross_result
    assert refresh.call_count == 0
    assert not any('"email"' in e and "owner@example.com" in e for e in cross_events)
