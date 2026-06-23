from fastapi import FastAPI

from hx_email.api.impl.auth_routes import register_auth_routes
from hx_email.api.impl.mail_routes import register_mail_routes
from hx_email.api.impl.platform_routes import register_platform_routes
from hx_email.api.impl.temp_mail_routes import register_temp_mail_routes
from hx_email.api.impl.workspace_routes import register_workspace_routes
from hx_email.config import Settings
from hx_email.server.mail.temp_mail import TempMailProvider
from hx_email.server.mail.verification import MailboxProvider


def register_routes(
    app: FastAPI,
    settings: Settings,
    mailbox_provider: MailboxProvider,
    temp_mail_providers: dict[str, TempMailProvider],
) -> None:
    register_system_routes(app)
    register_auth_routes(app, settings)
    register_workspace_routes(app, settings)
    register_platform_routes(app, settings)
    register_mail_routes(app, settings, mailbox_provider)
    register_temp_mail_routes(app, settings, temp_mail_providers)


def register_system_routes(app: FastAPI) -> None:
    @app.get("/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok", "service": "hx-email"}
