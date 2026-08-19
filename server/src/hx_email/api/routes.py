from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Body, FastAPI, Header, HTTPException, Response, status

from hx_email.api.audit_routes import register_audit_middleware, register_audit_routes
from hx_email.api.dependencies import (
    require_admin,
    require_admin_or_sync_key,
    require_user,
)
from hx_email.api.impl.auth_routes import register_auth_routes
from hx_email.api.impl.external import (
    register_external_message_routes,
    register_external_pool_routes,
    register_external_system_routes,
    register_external_temp_mail_routes,
)
from hx_email.api.impl.google_verification.admin_routes import (
    register_google_verification_routes,
)
from hx_email.api.impl.google_verification.serve_routes import (
    register_google_verification_serve_route,
)
from hx_email.api.impl.mail.pool import register_pool_admin_routes
from hx_email.api.impl.mail_routes import register_mail_routes
from hx_email.api.impl.messaging import (
    register_messaging_action_routes,
    register_messaging_event_routes,
    register_messaging_routes,
)
from hx_email.api.impl.overview import (
    register_notification_routes,
    register_overview_refresh_routes,
    register_overview_routes,
)
from hx_email.api.impl.platform_routes import register_platform_routes
from hx_email.api.impl.plugins import (
    register_plugin_config_routes,
    register_plugin_crud_routes,
)
from hx_email.api.impl.settings.cf_worker_sync import register_cf_worker_sync_route
from hx_email.api.impl.settings.settings_routes import register_settings_routes
from hx_email.api.impl.settings.settings_test_routes import register_settings_test_routes
from hx_email.api.impl.settings.update_routes import register_update_routes
from hx_email.api.impl.temp_mail_routes import register_temp_mail_routes
from hx_email.api.impl.workspace.routes import register_workspace_routes
from hx_email.config import Settings
from hx_email.server.data_transfer import (
    DataImportConflictError,
    DataImportInvalidError,
    export_core_data,
    import_core_data,
)
from hx_email.server.instance_backup import (
    InstanceBackupError,
    create_instance_backup,
    restore_instance_backup,
)
from hx_email.server.instance_backup.archive import MAX_ARCHIVE_BYTES
from hx_email.server.mail.impl.fetch.scheduler import get_polling_status
from hx_email.server.mail.temp_mail import TempMailProvider
from hx_email.server.mail.verification import MailboxProvider
from hx_email.server.sync.scheduler import get_sync_status
from hx_email.server.sync.service import SyncReport, apply_snapshot


def register_routes(
    app: FastAPI,
    settings: Settings,
    mailbox_provider: MailboxProvider,
    temp_mail_providers: dict[str, TempMailProvider],
    pause_scheduler: Callable[[], bool] | None = None,
    resume_scheduler: Callable[[bool], None] | None = None,
) -> None:
    register_audit_middleware(app, settings)

    # Health + static-file routes stay on app directly (no /api/v1 prefix)
    register_health_routes(app)
    register_static_routes(app, settings)
    register_google_verification_serve_route(app, settings)

    # All business API routes go under /api/v1
    api = APIRouter(prefix="/api/v1")

    register_system_routes(api, settings)
    register_auth_routes(api, settings)
    register_workspace_routes(api, settings)
    register_platform_routes(api, settings)
    register_mail_routes(api, settings, mailbox_provider)
    register_temp_mail_routes(api, settings, temp_mail_providers)
    register_overview_routes(api, settings)
    register_overview_refresh_routes(api, settings)
    register_notification_routes(api, settings)
    register_settings_routes(api, settings)
    register_settings_test_routes(api, settings)
    register_update_routes(api, settings)
    register_cf_worker_sync_route(api, settings)
    register_data_transfer_routes(api, settings, pause_scheduler, resume_scheduler)
    register_google_verification_routes(api, settings)
    register_pool_admin_routes(api, settings)
    register_audit_routes(api, settings)
    register_plugin_crud_routes(api, settings)
    register_plugin_config_routes(api, settings)
    register_messaging_routes(api, settings)
    register_messaging_action_routes(api, settings)
    register_messaging_event_routes(api, settings)

    app.include_router(api)

    # External API routes stay on app directly (already use /api/external/ prefix)
    register_external_routes(app, settings, mailbox_provider, temp_mail_providers)


def register_external_routes(
    app: FastAPI,
    settings: Settings,
    mailbox_provider: MailboxProvider,
    temp_mail_providers: dict[str, TempMailProvider],
) -> None:
    """Register external API routes secured by Authorization: Bearer (external API key)."""
    register_external_system_routes(app, settings)
    register_external_message_routes(app, settings, mailbox_provider, temp_mail_providers)
    register_external_pool_routes(app, settings)
    register_external_temp_mail_routes(app, settings, temp_mail_providers)


def register_health_routes(app: FastAPI) -> None:
    @app.get("/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok", "service": "hx-email"}

    @app.get("/healthz")
    def healthz() -> str:
        return "ok"


def register_static_routes(app: FastAPI, settings: Settings) -> None:
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


def register_system_routes(router: APIRouter, settings: Settings) -> None:
    @router.get("/csrf-token")
    def csrf_token() -> dict[str, str]:
        import secrets

        return {"csrf_token": secrets.token_hex(32)}

    @router.get("/bootstrap")
    def bootstrap(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        polling_status: dict[str, object] = get_polling_status(settings)
        return {
            "bootstrap": {
                "user_id": user.id,
                "is_admin": user.is_admin,
                "enable_auto_polling": polling_status["enabled"],
                "polling_interval": polling_status["interval_seconds"],
                "ui_layout_v2": {},
            }
        }

    @router.get("/scheduler/status")
    def scheduler_status(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return get_polling_status(settings)

    @router.get("/sync/status")
    def sync_status(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return get_sync_status(settings)

    @router.get("/system/diagnostics")
    def system_diagnostics(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_admin(settings, authorization)
        import platform
        import sys

        return {
            "platform": platform.platform(),
            "python_version": sys.version,
            "database_size_bytes": (
                settings.database_path.stat().st_size if settings.database_path.exists() else 0
            ),
        }

    @router.get("/system/upgrade-status")
    def system_upgrade_status(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        from hx_email.database import connect

        with connect(settings) as connection:
            version_row = connection.execute("PRAGMA user_version").fetchone()
            db_version: int = version_row[0] if version_row is not None else 0
        return {"db_version": db_version, "upgrade_needed": False}


def register_data_transfer_routes(
    router: APIRouter,
    settings: Settings,
    pause_scheduler: Callable[[], bool] | None = None,
    resume_scheduler: Callable[[bool], None] | None = None,
) -> None:
    @router.get("/data/export")
    def export_data(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_admin(settings, authorization)
        return export_core_data(settings, user.id)

    @router.post("/data/import", status_code=status.HTTP_201_CREATED)
    def import_data(
        payload: dict[str, Any],
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_admin(settings, authorization)
        try:
            return import_core_data(settings, user.id, payload)
        except DataImportConflictError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        except DataImportInvalidError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
            ) from error

    @router.get("/admin/backup/export")
    def export_instance_backup_data(
        authorization: Annotated[str | None, Header()] = None,
    ) -> Response:
        require_admin(settings, authorization)
        archive: bytes = create_instance_backup(settings)
        headers: dict[str, str] = {
            "Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="hx-email-instance-backup.zip"',
        }
        return Response(content=archive, media_type="application/zip", headers=headers)

    @router.get("/admin/sync/snapshot")
    def sync_snapshot_data(
        authorization: Annotated[str | None, Header()] = None,
    ) -> Response:
        require_admin_or_sync_key(settings, authorization)
        archive: bytes = create_instance_backup(settings)
        headers: dict[str, str] = {
            "Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="hx-email-sync-snapshot.zip"',
        }
        return Response(content=archive, media_type="application/zip", headers=headers)

    @router.post("/admin/sync/push")
    def sync_push_data(
        archive: Annotated[bytes, Body(media_type="application/zip")],
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_admin_or_sync_key(settings, authorization)
        if not archive or len(archive) > MAX_ARCHIVE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Push archive is empty or too large",
            )
        report: SyncReport = apply_snapshot(settings, archive, overwrite=False)
        if report.error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=report.error
            )
        return report.to_dict()

    @router.post("/admin/backup/import")
    def import_instance_backup_data(
        archive: Annotated[bytes, Body(media_type="application/zip")],
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_admin(settings, authorization)
        try:
            restore_instance_backup(settings, archive, pause_scheduler, resume_scheduler)
        except InstanceBackupError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
            ) from error
        return {"restored": True, "requires_relogin": True}
