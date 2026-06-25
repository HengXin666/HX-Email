"""Overview stats API endpoints: summary, verification, external-API, pool, activity."""

from typing import Annotated

from fastapi import APIRouter, Header

from hx_email.api.dependencies import require_user
from hx_email.config import Settings
from hx_email.server.workspace.impl.overview_service import (
    get_activity_stats,
    get_external_api_stats,
    get_overview_summary,
    get_pool_stats,
    get_verification_stats,
)


def register_overview_routes(router: APIRouter, settings: Settings) -> None:
    @router.get("/overview/summary")
    def overview_summary(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return get_overview_summary(settings)

    @router.get("/overview/verification")
    def overview_verification(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return get_verification_stats(settings)

    @router.get("/overview/verification-stats")
    def overview_verification_stats(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return get_verification_stats(settings)

    @router.get("/overview/external-api")
    def overview_external_api(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return get_external_api_stats(settings)

    @router.get("/overview/external-api-stats")
    def overview_external_api_stats(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return get_external_api_stats(settings)

    @router.get("/overview/pool")
    def overview_pool(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return get_pool_stats(settings)

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
