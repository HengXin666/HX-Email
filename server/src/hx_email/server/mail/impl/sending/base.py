from abc import ABC, abstractmethod
from email.message import Message
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hx_email.server.mail.impl.sending.credentials import SendCredentials


class EmailServerBase(ABC):
    provider: str
    smtp_host: str
    smtp_port: int
    security: str

    def req_email(
        self,
        credentials: "SendCredentials",
        recipient: str,
        subject: str,
        body: str,
    ) -> None:
        from email.message import EmailMessage

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = credentials.from_address
        message["To"] = recipient
        message.set_content(body)
        self.deliver(credentials, message)

    @abstractmethod
    def deliver(
        self,
        credentials: "SendCredentials",
        message: Message,
        *,
        proxy_url: str = "",
    ) -> None:
        raise NotImplementedError
