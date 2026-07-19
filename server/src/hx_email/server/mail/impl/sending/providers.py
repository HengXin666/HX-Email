import base64
import smtplib
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

from hx_email.server.mail.impl.sending.base import EmailServerBase

if TYPE_CHECKING:
    from hx_email.server.mail.impl.sending.credentials import SendCredentials


class SmtpEmailServerBase(EmailServerBase):
    provider: str = "custom"
    smtp_host: str = ""
    smtp_port: int = 587
    security: str = "starttls"

    def deliver(self, credentials: "SendCredentials", message: MIMEText) -> None:
        if credentials.security == "ssl":
            with smtplib.SMTP_SSL(
                credentials.smtp_host, credentials.smtp_port, timeout=15
            ) as server:
                server.login(credentials.username, credentials.password)
                server.send_message(message)
            return
        with smtplib.SMTP(credentials.smtp_host, credentials.smtp_port, timeout=15) as server:
            server.starttls()
            if credentials.credential_strategy == "gmail_oauth_smtp":
                authenticate_xoauth2(server, credentials.username, credentials.password)
            else:
                server.login(credentials.username, credentials.password)
            server.send_message(message)


def authenticate_xoauth2(server: smtplib.SMTP, username: str, access_token: str) -> None:
    auth_bytes: bytes = f"user={username}\x01auth=Bearer {access_token}\x01\x01".encode()
    auth_value: str = base64.b64encode(auth_bytes).decode("ascii")
    result: tuple[int, bytes] = server.docmd("AUTH", f"XOAUTH2 {auth_value}")
    code: int = result[0]
    response: bytes = result[1]
    if code != 235:
        raise smtplib.SMTPAuthenticationError(code, response)


class OutlookEmailServer(SmtpEmailServerBase):
    provider = "outlook"
    smtp_host = "smtp-mail.outlook.com"


class GmailEmailServer(SmtpEmailServerBase):
    provider = "gmail"
    smtp_host = "smtp.gmail.com"


class QQEmailServer(SmtpEmailServerBase):
    provider = "qq"
    smtp_host = "smtp.qq.com"


class NetEase163EmailServer(SmtpEmailServerBase):
    provider = "163"
    smtp_host = "smtp.163.com"
    smtp_port = 465
    security = "ssl"


class NetEase126EmailServer(SmtpEmailServerBase):
    provider = "126"
    smtp_host = "smtp.126.com"
    smtp_port = 465
    security = "ssl"


class YahooEmailServer(SmtpEmailServerBase):
    provider = "yahoo"
    smtp_host = "smtp.mail.yahoo.com"
