from abc import ABC, abstractmethod
from email.mime.text import MIMEText
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
        message = MIMEText(body, "plain", "utf-8")
        message["Subject"] = subject
        message["From"] = credentials.from_address
        message["To"] = recipient
        self.deliver(credentials, message)

    @abstractmethod
    def deliver(self, credentials: "SendCredentials", message: MIMEText) -> None:
        raise NotImplementedError
