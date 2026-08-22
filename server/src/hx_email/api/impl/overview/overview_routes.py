"""Overview stats API endpoints: summary, verification, external-API, pool, activity."""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException

from hx_email.api.dependencies import require_user
from hx_email.config import Settings
from hx_email.server.workspace.impl.overview_service import (
    get_activity_stats,
    get_external_api_stats,
    get_overview_summary,
    get_pool_stats,
    get_verification_stats,
)
from hx_email.server.workspace.overview import get_account_stats


def register_overview_routes(router: APIRouter, settings: Settings) -> None:
    @router.get("/overview/account-stats")
    def account_stats(
        authorization: Annotated[str | None, Header()] = None,
        provider: str | None = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        # UI 侧使用 microsoft/google, 后端账号表使用 outlook/gmail
        provider_map: dict[str, str] = {"microsoft": "outlook", "google": "gmail"}
        backend_provider: str | None = provider_map.get(provider or "", provider)
        if backend_provider is not None and backend_provider not in ("outlook", "gmail"):
            raise HTTPException(
                status_code=422,
                detail="provider must be microsoft/google/outlook/gmail",
            )
        return get_account_stats(settings, user.id, provider=backend_provider)

    @router.get("/overview/summary")
    def overview_summary(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return get_overview_summary(settings)

    # Canonical paths use the -stats suffix; the short forms are legacy aliases
    @router.get("/overview/verification", deprecated=True)
    @router.get("/overview/verification-stats")
    def overview_verification_stats(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return get_verification_stats(settings)

    @router.get("/overview/external-api", deprecated=True)
    @router.get("/overview/external-api-stats")
    def overview_external_api_stats(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return get_external_api_stats(settings)

    @router.get("/overview/pool", deprecated=True)
    @router.get("/overview/pool-stats")
    def overview_pool_stats(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return get_pool_stats(settings)

    @router.get("/overview/activity")
    def overview_activity(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return get_activity_stats(settings)
