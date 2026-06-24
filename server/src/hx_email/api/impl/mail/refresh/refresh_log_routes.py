"""Refresh log query route registration.

Endpoints for querying refresh history, failed logs, invalid token
candidates, and aggregate refresh statistics.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, Header, Query

from hx_email.api.dependencies import require_user
from hx_email.config import Settings
from hx_email.server.mail.impl.refresh_log_service import (
    get_failed_refresh_logs,
    get_invalid_token_candidates,
    get_refresh_logs,
    get_refresh_stats,
)


def register_refresh_log_routes(app: FastAPI, settings: Settings) -> None:
    @app.get("/email-accounts/refresh-logs")
    def list_refresh_logs(
        limit: Annotated[int, Query(ge=1, le=500)] = 200,
        offset: Annotated[int, Query(ge=0)] = 0,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return get_refresh_logs(settings, limit=limit, offset=offset)

    @app.get("/email-accounts/{account_id}/refresh-logs")
    def list_account_refresh_logs(
        account_id: int,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return get_refresh_logs(settings, account_id=account_id, limit=limit, offset=offset)

    @app.get("/email-accounts/refresh-logs/failed")
    def list_failed_refresh_logs(
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return {"logs": get_failed_refresh_logs(settings, limit=limit)}

    @app.get("/email-accounts/invalid-token-candidates")
    def list_invalid_token_candidates(
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return get_invalid_token_candidates(settings, limit=limit, offset=offset)

    @app.get("/email-accounts/refresh-stats")
    def get_stats(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return get_refresh_stats(settings)
