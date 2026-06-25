"""Overview refresh-related routes: failed refresh logs, refresh stats, invalid tokens."""

from typing import Annotated

from fastapi import APIRouter, Header, Query

from hx_email.api.dependencies import require_user
from hx_email.config import Settings
from hx_email.server.mail.impl.refresh_log_service import (
    get_failed_refresh_logs,
    get_invalid_token_candidates,
    get_refresh_stats,
)


def register_overview_refresh_routes(router: APIRouter, settings: Settings) -> None:
    @router.get("/overview/refresh-failed")
    def overview_refresh_failed(
        limit: int = Query(default=50, ge=1, le=500),
        authorization: Annotated[str | None, Header()] = None,
    ) -> list[dict[str, object]]:
        require_user(settings, authorization)
        return get_failed_refresh_logs(settings, limit=limit)

    @router.get("/overview/refresh-stats")
    def overview_refresh_stats(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return get_refresh_stats(settings)

    @router.get("/overview/invalid-token-candidates")
    def overview_invalid_token_candidates(
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return get_invalid_token_candidates(settings, limit=limit, offset=offset)
