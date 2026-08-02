import base64
import smtplib
import socket
from email.message import Message
from typing import TYPE_CHECKING

from hx_email.server.mail.imap.impl.proxy import http_connect_via_proxy
from hx_email.server.mail.impl.sending.base import EmailServerBase

if TYPE_CHECKING:
    from hx_email.server.mail.impl.sending.credentials import SendCredentials


class SmtpDeliveryError(RuntimeError):
    """Actionable error raised when an SMTP delivery step fails."""


class SmtpProxyClient(smtplib.SMTP):
    """SMTP client whose TCP connection is opened through HTTP CONNECT."""

    def __init__(self, host: str, port: int, proxy_url: str, timeout: float) -> None:
        self._proxy_url: str = proxy_url
        super().__init__(host, port, timeout=timeout)

    def _get_socket(self, host: str, port: int, timeout: float | None) -> socket.socket:
        return http_connect_via_proxy(self._proxy_url, host, port, timeout or 30)


class SmtpProxySslClient(smtplib.SMTP_SSL):
    """Implicit-SSL SMTP client whose TCP connection is opened through HTTP CONNECT."""

    def __init__(self, host: str, port: int, proxy_url: str, timeout: float) -> None:
        self._proxy_url: str = proxy_url
        super().__init__(host, port, timeout=timeout)

    def _get_socket(self, host: str, port: int, timeout: float | None) -> socket.socket:
        raw_socket: socket.socket = http_connect_via_proxy(
            self._proxy_url, host, port, timeout or 30
        )
        try:
            return self.context.wrap_socket(raw_socket, server_hostname=host)
        except Exception:
            raw_socket.close()
            raise


class SmtpEmailServerBase(EmailServerBase):
    provider: str = "custom"
    smtp_host: str = ""
    smtp_port: int = 587
    security: str = "starttls"

    def deliver(
        self,
        credentials: "SendCredentials",
        message: Message,
        *,
        proxy_url: str = "",
    ) -> None:
        stage: str = "SMTP connection"
        try:
            if credentials.security == "ssl":
                ssl_server = (
                    SmtpProxySslClient(
                        credentials.smtp_host,
                        credentials.smtp_port,
                        proxy_url,
                        timeout=15,
                    )
                    if proxy_url
                    else smtplib.SMTP_SSL(credentials.smtp_host, credentials.smtp_port, timeout=15)
                )
                with ssl_server as smtp_client:
                    stage = "SMTP authentication"
                    if credentials.username and credentials.password:
                        smtp_client.login(credentials.username, credentials.password)
                    stage = "message submission"
                    smtp_client.send_message(message)
                return
            starttls_server = (
                SmtpProxyClient(
                    credentials.smtp_host,
                    credentials.smtp_port,
                    proxy_url,
                    timeout=15,
                )
                if proxy_url
                else smtplib.SMTP(credentials.smtp_host, credentials.smtp_port, timeout=15)
            )
            with starttls_server as smtp_client:
                stage = "STARTTLS handshake"
                smtp_client.starttls()
                stage = "SMTP authentication"
                if credentials.username and credentials.password:
                    if credentials.credential_strategy == "gmail_oauth_smtp":
                        authenticate_xoauth2(
                            smtp_client, credentials.username, credentials.password
                        )
                    else:
                        smtp_client.login(credentials.username, credentials.password)
                stage = "message submission"
                smtp_client.send_message(message)
        except smtplib.SMTPServerDisconnected as error:
            raise SmtpDeliveryError(
                f"SMTP server closed the connection during {stage} at "
                f"{credentials.smtp_host}:{credentials.smtp_port} "
                f"({credentials.security.upper()}). "
                "Check that the SMTP host, port, and security mode match "
                "(465=SSL, 587/25=STARTTLS)."
                f" Original error: {str(error).strip()}"
            ) from error
        except smtplib.SMTPAuthenticationError as error:
            raise SmtpDeliveryError(
                f"SMTP authentication failed at {credentials.smtp_host}:{credentials.smtp_port} "
                f"({credentials.security.upper()}). Check the app password or OAuth permission."
            ) from error
        except smtplib.SMTPConnectError as error:
            raise SmtpDeliveryError(
                f"Could not connect to SMTP server {credentials.smtp_host}:{credentials.smtp_port} "
                f"({credentials.security.upper()}): {str(error).strip()}"
            ) from error
        except smtplib.SMTPException as error:
            raise SmtpDeliveryError(
                f"SMTP {stage.lower()} failed at {credentials.smtp_host}:{credentials.smtp_port}: "
                f"{str(error).strip()}"
            ) from error
        except OSError as error:
            raise SmtpDeliveryError(
                f"Could not connect to SMTP server {credentials.smtp_host}:{credentials.smtp_port} "
                f"({credentials.security.upper()}): {str(error).strip()}"
            ) from error
        except Exception as error:
            raise SmtpDeliveryError(
                f"SMTP {stage} failed at {credentials.smtp_host}:{credentials.smtp_port}: "
                f"{str(error).strip()}"
            ) from error


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


class AliyunEmailServer(SmtpEmailServerBase):
    provider = "aliyun"
    smtp_host = "smtp.aliyun.com"
    smtp_port = 465
    security = "ssl"
