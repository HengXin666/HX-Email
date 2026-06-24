from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, Response, status

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
from hx_email.api.impl.plugins import (
    register_plugin_config_routes,
    register_plugin_crud_routes,
)
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
    register_system_routes(app, settings)
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
    register_plugin_crud_routes(app, settings)
    register_plugin_config_routes(app, settings)
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


def register_system_routes(app: FastAPI, settings: Settings) -> None:
    @app.get("/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok", "service": "hx-email"}

    @app.get("/healthz")
    def healthz() -> str:
        return "ok"

    @app.get("/csrf-token")
    def csrf_token() -> dict[str, str]:
        import secrets

        return {"csrf_token": secrets.token_hex(32)}

    @app.get("/bootstrap")
    def bootstrap(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        return {
            "bootstrap": {
                "user_id": user.id,
                "is_admin": user.is_admin,
                "enable_auto_polling": True,
                "polling_interval": 30,
                "ui_layout_v2": {},
            }
        }

    @app.get("/scheduler/status")
    def scheduler_status(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return {
            "running": True,
            "last_run": "",
            "next_run": "",
            "tasks": {
                "scheduled_refresh": "idle",
                "auto_poll": "idle",
            },
        }

    @app.get("/system/diagnostics")
    def system_diagnostics(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        import platform
        import sys

        return {
            "platform": platform.platform(),
            "python_version": sys.version,
            "database_path": str(settings.database_path),
            "database_size_bytes": (
                settings.database_path.stat().st_size if settings.database_path.exists() else 0
            ),
        }

    @app.get("/system/upgrade-status")
    def system_upgrade_status(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        from hx_email.database import connect

        with connect(settings) as connection:
            version_row = connection.execute("PRAGMA user_version").fetchone()
            db_version: int = version_row[0] if version_row is not None else 0
        return {"db_version": db_version, "upgrade_needed": False}

    @app.get("/img/{filename:path}")
    def serve_image(filename: str) -> Response:
        from fastapi.responses import FileResponse

        static_dir = settings.data_dir / "static" / "img"
        file_path = (static_dir / filename).resolve()
        if not str(file_path).startswith(str(static_dir.resolve())):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        if not file_path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        return FileResponse(file_path)


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
