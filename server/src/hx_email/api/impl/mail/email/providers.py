"""Email provider listing constants and route."""

from typing import Annotated

from fastapi import APIRouter, Header

from hx_email.api.dependencies import require_user
from hx_email.config import Settings
from hx_email.server.mail.verification import MailboxProvider

SUPPORTED_PROVIDERS: list[dict[str, object]] = [
    {
        "id": "outlook",
        "name": "Outlook / Hotmail",
        "type": "oauth",
        "domains": ["outlook.com", "hotmail.com", "live.com", "live.cn"],
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
        "smtp_host": "smtp-mail.outlook.com",
        "smtp_port": 587,
    },
    {
        "id": "gmail",
        "name": "Gmail",
        "type": "oauth",
        "domains": ["gmail.com", "googlemail.com"],
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
    },
    {
        "id": "qq",
        "name": "QQ Mail",
        "type": "password",
        "domains": ["qq.com", "foxmail.com"],
        "imap_host": "imap.qq.com",
        "imap_port": 993,
        "smtp_host": "smtp.qq.com",
        "smtp_port": 587,
    },
    {
        "id": "163",
        "name": "NetEase 163",
        "type": "password",
        "domains": ["163.com"],
        "imap_host": "imap.163.com",
        "imap_port": 993,
        "smtp_host": "smtp.163.com",
        "smtp_port": 465,
    },
    {
        "id": "126",
        "name": "NetEase 126",
        "type": "password",
        "domains": ["126.com"],
        "imap_host": "imap.126.com",
        "imap_port": 993,
        "smtp_host": "smtp.126.com",
        "smtp_port": 465,
    },
    {
        "id": "yahoo",
        "name": "Yahoo Mail",
        "type": "oauth",
        "domains": ["yahoo.com", "yahoo.co.jp", "yahoo.co.uk"],
        "imap_host": "imap.mail.yahoo.com",
        "imap_port": 993,
        "smtp_host": "smtp.mail.yahoo.com",
        "smtp_port": 587,
    },
    {
        "id": "custom",
        "name": "Custom IMAP",
        "type": "custom",
        "domains": [],
        "imap_host": "",
        "imap_port": 993,
        "smtp_host": "",
        "smtp_port": 587,
    },
]


def register_provider_routes(
    router: APIRouter,
    settings: Settings,
    mailbox_provider: MailboxProvider,
) -> None:
    """Register GET /providers endpoint."""

    @router.get("/providers")
    def list_providers(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, list[dict[str, object]]]:
        require_user(settings, authorization)
        return {"providers": SUPPORTED_PROVIDERS}
