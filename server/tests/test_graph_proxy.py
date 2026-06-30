from __future__ import annotations

from unittest.mock import Mock, patch

from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.mail import EmailAccountMailbox
from hx_email.server.mail.graph.graph_client import GraphMailProvider
from hx_email.server.mail.graph.graph_helpers import build_proxies


def test_build_proxies_matches_reference_project() -> None:
    assert build_proxies("http://127.0.0.1:2334") == {
        "http": "http://127.0.0.1:2334",
        "https": "http://127.0.0.1:2334",
    }


def test_graph_provider_uses_group_proxy_for_token_and_messages(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    migrate(settings)
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
                (id, user_id, provider, primary_address, client_id, refresh_token, group_id)
            VALUES (1, 1, 'outlook', 'owner@example.com', 'cid', 'rt', 10)
            """
        )

    token_response = Mock()
    token_response.status_code = 200
    token_response.json.return_value = {"access_token": "token", "expires_in": 3600}
    messages_response = Mock()
    messages_response.status_code = 200
    messages_response.json.return_value = {"value": []}
    expected_proxies = {
        "http": "http://127.0.0.1:2334",
        "https": "http://127.0.0.1:2334",
    }

    with (
        patch(
            "hx_email.server.mail.graph.graph_helpers.requests.post", return_value=token_response
        ) as post,
        patch(
            "hx_email.server.mail.graph.graph_helpers.requests.get", return_value=messages_response
        ) as get,
    ):
        result = GraphMailProvider(settings).read_messages_result(
            EmailAccountMailbox(id=1, provider="outlook", primary_address="owner@example.com")
        )

    assert result.succeeded is True
    assert post.call_args.kwargs["proxies"] == expected_proxies
    assert get.call_args.kwargs["proxies"] == expected_proxies
