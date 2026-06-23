from typing import cast

from fastapi import FastAPI

from hx_email.api.routes import register_routes
from hx_email.config import Settings
from hx_email.server.mail.temp_mail import TempMailProvider
from hx_email.server.mail.verification import EmptyMailboxProvider, MailboxProvider


def create_app(
    settings: Settings | None = None,
    mailbox_provider: MailboxProvider | None = None,
    temp_mail_providers: dict[str, TempMailProvider] | None = None,
) -> FastAPI:
    resolved_settings: Settings = settings or Settings()
    resolved_mailbox_provider: MailboxProvider = cast(
        MailboxProvider,
        mailbox_provider or EmptyMailboxProvider(),
    )
    app = FastAPI(title="HX Email")
    register_routes(
        app,
        resolved_settings,
        resolved_mailbox_provider,
        temp_mail_providers or {},
    )
    return app


app: FastAPI = create_app()
