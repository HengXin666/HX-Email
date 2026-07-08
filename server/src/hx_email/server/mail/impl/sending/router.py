from hx_email.server.mail.impl.sending.base import EmailServerBase
from hx_email.server.mail.impl.sending.providers import (
    GmailEmailServer,
    NetEase126EmailServer,
    NetEase163EmailServer,
    OutlookEmailServer,
    QQEmailServer,
    SmtpEmailServerBase,
    YahooEmailServer,
)

server_map: dict[str, EmailServerBase] = {
    server.provider: server
    for server in (
        OutlookEmailServer(),
        GmailEmailServer(),
        QQEmailServer(),
        NetEase163EmailServer(),
        NetEase126EmailServer(),
        YahooEmailServer(),
    )
}


def get_email_server(provider: str, smtp_host: str = "", smtp_port: int = 587) -> EmailServerBase:
    key: str = provider.strip().lower()
    if key in server_map:
        return server_map[key]
    server = SmtpEmailServerBase()
    server.smtp_host = smtp_host
    server.smtp_port = smtp_port
    server.security = "ssl" if smtp_port == 465 else "starttls"
    return server
