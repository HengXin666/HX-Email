from fastapi import FastAPI

from hx_email.api.impl.mail import (
    register_email_account_routes,
    register_mail_pool_routes,
    register_usable_email_routes,
)
from hx_email.config import Settings
from hx_email.server.mail.verification import MailboxProvider


def register_mail_routes(
    app: FastAPI,
    settings: Settings,
    mailbox_provider: MailboxProvider,
) -> None:
    register_usable_email_routes(app, settings, mailbox_provider)
    register_mail_pool_routes(app, settings)
    register_email_account_routes(app, settings)
