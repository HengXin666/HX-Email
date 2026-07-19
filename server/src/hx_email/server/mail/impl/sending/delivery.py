from dataclasses import replace

from hx_email.config import Settings
from hx_email.security import persist_rotated_refresh_token
from hx_email.server.mail.google_oauth import get_google_access_token
from hx_email.server.mail.graph import graph_helpers
from hx_email.server.mail.imap.impl.proxy import load_group_proxy
from hx_email.server.mail.impl.sending.credentials import SendCredentials
from hx_email.server.mail.impl.sending.router import get_email_server


def deliver_debug_email(
    settings: Settings,
    credentials: SendCredentials,
    recipient: str,
    subject: str,
    body: str,
) -> None:
    if credentials.credential_strategy == "outlook_graph_send_mail":
        graph_proxy_url: str = load_group_proxy(settings, credentials.email_account_id)
        graph_access_token, _tenant, rotated_token = graph_helpers.try_get_graph_token(
            credentials.client_id, credentials.refresh_token, graph_proxy_url
        )
        persist_rotated_refresh_token(
            settings,
            credentials.email_account_id,
            credentials.refresh_token,
            rotated_token,
        )
        graph_helpers.graph_send_mail(
            graph_access_token,
            recipient=recipient,
            subject=subject,
            body=body,
            proxy_url=graph_proxy_url,
        )
        return
    if credentials.credential_strategy == "gmail_oauth_smtp":
        google_proxy_url: str = load_group_proxy(settings, credentials.email_account_id)
        google_access_token: str = get_google_access_token(
            settings,
            credentials.client_id,
            credentials.refresh_token,
            google_proxy_url,
        )
        credentials = replace(credentials, password=google_access_token)
    server = get_email_server(credentials.provider, credentials.smtp_host, credentials.smtp_port)
    server.req_email(credentials, recipient, subject, body)
