import smtplib
from email.mime.text import MIMEText

from hx_email.server.mail.impl.sending.credentials import SendCredentials


def deliver_debug_email(
    credentials: SendCredentials,
    recipient: str,
    subject: str,
    body: str,
) -> None:
    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = subject
    message["From"] = credentials.from_address
    message["To"] = recipient
    if credentials.security == "ssl":
        with smtplib.SMTP_SSL(credentials.smtp_host, credentials.smtp_port, timeout=15) as server:
            server.login(credentials.username, credentials.password)
            server.send_message(message)
        return
    with smtplib.SMTP(credentials.smtp_host, credentials.smtp_port, timeout=15) as server:
        server.starttls()
        server.login(credentials.username, credentials.password)
        server.send_message(message)
