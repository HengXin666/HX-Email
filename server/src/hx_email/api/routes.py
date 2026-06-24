from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, status

from hx_email.api.audit_routes import register_audit_routes
from hx_email.api.dependencies import require_user
from hx_email.api.impl.auth_routes import register_auth_routes
from hx_email.api.impl.external import (
    register_external_message_routes,
    register_external_pool_routes,
    register_external_system_routes,
    register_external_temp_mail_routes,
)
from hx_email.api.impl.mail.pool import register_pool_admin_routes
from hx_email.api.impl.mail_routes import register_mail_routes
from hx_email.api.impl.overview import (
    register_overview_refresh_routes,
    register_overview_routes,
)
from hx_email.api.impl.platform_routes import register_platform_routes
from hx_email.api.impl.settings.settings_routes import register_settings_routes
from hx_email.api.impl.settings.settings_test_routes import register_settings_test_routes
from hx_email.api.impl.temp_mail_routes import register_temp_mail_routes
from hx_email.api.impl.workspace_routes import register_workspace_routes
from hx_email.config import Settings
from hx_email.server.data_transfer import (
    DataImportConflictError,
    export_core_data,
    import_core_data,
)
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
    register_overview_routes(app, settings)
    register_overview_refresh_routes(app, settings)
    register_settings_routes(app, settings)
    register_settings_test_routes(app, settings)
    register_data_transfer_routes(app, settings)
    register_pool_admin_routes(app, settings)
    register_audit_routes(app, settings)
    register_external_routes(app, settings, mailbox_provider, temp_mail_providers)


def register_external_routes(
    app: FastAPI,
    settings: Settings,
    mailbox_provider: MailboxProvider,
    temp_mail_providers: dict[str, TempMailProvider],
) -> None:
    """Register external API routes secured by X-API-Key."""
    register_external_system_routes(app, settings)
    register_external_message_routes(app, settings, mailbox_provider)
    register_external_pool_routes(app, settings)
    register_external_temp_mail_routes(app, settings, temp_mail_providers)


def register_system_routes(app: FastAPI) -> None:
    @app.get("/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok", "service": "hx-email"}


def register_data_transfer_routes(app: FastAPI, settings: Settings) -> None:
    @app.get("/data/export")
    def export_data(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        return export_core_data(settings, user.id)

    @app.post("/data/import", status_code=status.HTTP_201_CREATED)
    def import_data(
        payload: dict[str, Any],
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        try:
            return import_core_data(settings, user.id, payload)
        except DataImportConflictError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
