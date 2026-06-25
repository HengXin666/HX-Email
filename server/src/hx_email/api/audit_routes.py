from typing import Annotated

from fastapi import APIRouter, Header, Query

from hx_email.api.dependencies import require_admin
from hx_email.config import Settings
from hx_email.server.admin import get_audit_logs


def register_audit_routes(router: APIRouter, settings: Settings) -> None:
    @router.get("/audit-logs")
    def list_audit_logs(
        authorization: Annotated[str | None, Header()] = None,
        limit: int = Query(50),
        offset: int = Query(0),
        action: str | None = Query(None),
        resource_type: str | None = Query(None),
    ) -> dict[str, object]:
        require_admin(settings, authorization)
        return get_audit_logs(
            settings,
            limit=limit,
            offset=offset,
            action=action,
            resource_type=resource_type,
        )
