from __future__ import annotations

from unittest.mock import Mock, patch

from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.security import decrypt_secret
from hx_email.server.mail.impl.oauth_tool import try_refresh_oauth_token
from hx_email.server.mail.impl.refresh_service import (
    refresh_selected_accounts,
    refresh_single_account,
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
        "hx_email.server.mail.impl.refresh_service.try_refresh_provider_oauth_token",
        return_value={"success": True, "message": "ok", "error_detail": ""},
    ) as refresh:
        result = refresh_single_account(settings, 1, EmptyMailboxProvider())

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
        result = refresh_single_account(settings, 1, EmptyMailboxProvider())

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
        events = list(refresh_selected_accounts(settings, [1], EmptyMailboxProvider()))

    assert any("progress" in event for event in events)
    assert refresh.call_args.kwargs["proxy_url"] == "http://127.0.0.1:2334"


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
