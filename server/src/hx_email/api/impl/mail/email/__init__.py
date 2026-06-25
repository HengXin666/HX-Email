from fastapi import APIRouter

from hx_email.api.impl.mail.email.providers import register_provider_routes
from hx_email.api.impl.mail.email.routes import register_email_ops_routes
from hx_email.config import Settings
from hx_email.server.mail.verification import MailboxProvider


def register_email_routes(
    router: APIRouter,
    settings: Settings,
    mailbox_provider: MailboxProvider,
) -> None:
    register_provider_routes(router, settings, mailbox_provider)
    register_email_ops_routes(router, settings, mailbox_provider)


__all__ = ["register_email_routes"]
