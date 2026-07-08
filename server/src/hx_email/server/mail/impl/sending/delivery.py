from hx_email.server.mail.impl.sending.credentials import SendCredentials
from hx_email.server.mail.impl.sending.router import get_email_server


def deliver_debug_email(
    credentials: SendCredentials,
    recipient: str,
    subject: str,
    body: str,
) -> None:
    server = get_email_server(credentials.provider, credentials.smtp_host, credentials.smtp_port)
    server.req_email(credentials, recipient, subject, body)
