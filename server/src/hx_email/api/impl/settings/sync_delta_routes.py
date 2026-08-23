"""Incremental sync endpoints: exchange WAL change packages with sync peers.

GET  /api/v1/admin/sync/delta?after=<seq>  主实例返回自水位以来的增量包
POST /api/v1/admin/sync/delta              从实例推送本地增量包 (union merge)
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, HTTPException, status

from hx_email.api.dependencies import require_admin_or_sync_key, require_user
from hx_email.config import Settings
from hx_email.server.sync.delta import apply_delta_package, build_delta_package
from hx_email.server.sync.impl.client import redact_sync_url
from hx_email.server.sync.scheduler import get_sync_status
from hx_email.server.sync.watermark import SyncWatermark


def register_sync_delta_routes(router: APIRouter, settings: Settings) -> None:
    @router.get("/sync/status")
    def sync_status(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return get_sync_status(settings)

    @router.get("/admin/sync/delta")
    def sync_delta_data(
        after: int = 0,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_admin_or_sync_key(settings, authorization)
        payload, _ = build_delta_package(settings, SyncWatermark(last_push_seq=after))
        return payload

    @router.post("/admin/sync/delta")
    def sync_delta_push(
        payload: Annotated[dict[str, Any], Body()],
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_admin_or_sync_key(settings, authorization)
        try:
            tables: dict[str, int] = apply_delta_package(settings, payload)
        except (ValueError, OSError) as error:
            detail: str = redact_sync_url(settings, str(error))
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail
            ) from error
        return {"tables": tables}
