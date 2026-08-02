from dataclasses import replace
from email.message import EmailMessage

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
    proxy_url: str = (
        load_group_proxy(settings, credentials.email_account_id)
        if credentials.email_account_id
        else ""
    )
    if credentials.credential_strategy == "outlook_graph_send_mail":
        graph_access_token, _tenant, rotated_token = graph_helpers.try_get_graph_token(
            credentials.client_id, credentials.refresh_token, proxy_url
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
            proxy_url=proxy_url,
        )
        return
    if credentials.credential_strategy == "gmail_oauth_smtp":
        google_access_token: str = get_google_access_token(
            settings,
            credentials.client_id,
            credentials.refresh_token,
            proxy_url,
        )
        credentials = replace(credentials, password=google_access_token)
    deliver_smtp_message(credentials, recipient, subject, body, proxy_url=proxy_url)


def deliver_smtp_email(
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    recipient: str,
    subject: str,
    body: str,
    reply_to: str = "",
    proxy_url: str = "",
) -> None:
    """Send through a manually configured SMTP endpoint with shared diagnostics."""
    credentials = SendCredentials(
        usable_email_id=0,
        email_account_id=0,
        provider="custom",
        from_address=smtp_user or "test@example.com",
        username=smtp_user,
        password=smtp_password,
        client_id="",
        refresh_token="",
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        security="ssl" if smtp_port == 465 else "starttls",
        credential_strategy="manual_smtp",
    )
    deliver_smtp_message(
        credentials,
        recipient,
        subject,
        body,
        reply_to=reply_to,
        proxy_url=proxy_url,
    )


def deliver_smtp_message(
    credentials: SendCredentials,
    recipient: str,
    subject: str,
    body: str,
    reply_to: str = "",
    proxy_url: str = "",
) -> None:
    """Build and deliver one SMTP message using the shared provider implementation."""
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = credentials.from_address
    message["To"] = recipient
    if reply_to:
        message["Reply-To"] = reply_to
    message.set_content(body)
    server = get_email_server(credentials.provider, credentials.smtp_host, credentials.smtp_port)
    server.deliver(credentials, message, proxy_url=proxy_url)
