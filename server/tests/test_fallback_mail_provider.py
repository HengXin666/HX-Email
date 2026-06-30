from __future__ import annotations

from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.mail import EmailAccountMailbox, MailboxMessage
from hx_email.server.mail.graph.fallback_provider import FallbackMailProvider
from hx_email.server.mail.graph.graph_client import GraphReadResult


def test_fallback_provider_keeps_graph_first_when_group_proxy_is_configured(tmp_path) -> None:
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

    expected = [
        MailboxMessage(
            recipient_address="owner@example.com",
            subject="Proxy message",
            body="Body",
        )
    ]
    provider = FallbackMailProvider(settings)

    provider._graph.read_messages_result = lambda *args, **kwargs: GraphReadResult(expected, True)
    provider._imap.read_messages = lambda *args, **kwargs: [
        MailboxMessage(recipient_address="owner@example.com", subject="IMAP", body="Body")
    ]

    messages = provider.read_messages(
        EmailAccountMailbox(id=1, provider="outlook", primary_address="owner@example.com")
    )

    assert messages == expected
