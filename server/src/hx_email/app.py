from fastapi import FastAPI

from hx_email.api.routes import register_routes
from hx_email.config import Settings
from hx_email.server.mail.graph.fallback_provider import FallbackMailProvider
from hx_email.server.mail.impl.email_fetch_service import start_background_fetch
from hx_email.server.mail.temp_mail import TempMailProvider
from hx_email.server.mail.verification import MailboxProvider


def create_app(
    settings: Settings | None = None,
    mailbox_provider: MailboxProvider | None = None,
    temp_mail_providers: dict[str, TempMailProvider] | None = None,
) -> FastAPI:
    resolved_settings: Settings = settings or Settings()
    resolved_mailbox_provider: MailboxProvider = mailbox_provider or FallbackMailProvider(
        resolved_settings
    )
    app = FastAPI(title="HX Email")
    register_routes(
        app,
        resolved_settings,
        resolved_mailbox_provider,
        temp_mail_providers or {},
    )

    # Start background email fetcher (runs every 120 seconds)
    @app.on_event("startup")
    def _start_bg_fetch() -> None:
        start_background_fetch(resolved_settings, interval=120)

    @app.on_event("shutdown")
    def _stop_bg_fetch() -> None:
        from hx_email.server.mail.impl.email_fetch_service import stop_background_fetch

        stop_background_fetch()

    return app


app: FastAPI = create_app()
