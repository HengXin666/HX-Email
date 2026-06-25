from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, status

from hx_email.api.dependencies import require_admin
from hx_email.api.schemas import PoolAdminAction
from hx_email.config import Settings
from hx_email.server.admin import (
    execute_pool_action,
    list_pool_accounts,
)


def register_pool_admin_routes(router: APIRouter, settings: Settings) -> None:
    @router.get("/pool-admin/accounts")
    def get_pool_admin_accounts(
        authorization: Annotated[str | None, Header()] = None,
        in_pool: str | None = Query(None),
        pool_status: str | None = Query(None),
        provider: str | None = Query(None),
        group_id: int | None = Query(None),
        search: str | None = Query(None),
        page: int = Query(1),
        page_size: int = Query(20),
    ) -> dict[str, object]:
        require_admin(settings, authorization)
        filters: dict[str, object] = {
            "in_pool": in_pool,
            "pool_status": pool_status,
            "provider": provider,
            "group_id": group_id,
            "search": search,
            "page": page,
            "page_size": page_size,
        }
        return list_pool_accounts(settings, filters)

    @router.post("/pool-admin/accounts/{account_id}/action")
    def pool_admin_action(
        account_id: int,
        payload: PoolAdminAction,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_admin(settings, authorization)
        try:
            return execute_pool_action(
                settings,
                account_id,
                payload.action,
                payload.model_dump(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
