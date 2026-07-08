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
            server.login(credentials.username, credentials.password)
            server.send_message(message)


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
