from hx_email.config import Settings
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
        proxy_url: str = load_group_proxy(settings, credentials.email_account_id)
        access_token, _tenant = graph_helpers.try_get_graph_token(
            credentials.client_id, credentials.refresh_token, proxy_url
        )
        graph_helpers.graph_send_mail(
            access_token,
            recipient=recipient,
            subject=subject,
            body=body,
            proxy_url=proxy_url,
        )
        return
    server = get_email_server(credentials.provider, credentials.smtp_host, credentials.smtp_port)
    server.req_email(credentials, recipient, subject, body)
