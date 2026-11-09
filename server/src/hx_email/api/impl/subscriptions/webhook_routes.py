"""REST for webhook subscriptions: delivery log, manual redelivery, test ping, secret rotation.

All short sync calls in the thread pool. Redelivery wakes the dispatcher so a revived
batch goes out at once instead of waiting for the next due row.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Query

from hx_email.api.impl.gateway.auth import caller_user_id
from hx_email.config import Settings
from hx_email.server.access.scopes import SUBSCRIPTIONS
from hx_email.server.gateway.impl.dispatch import DISPATCHER
from hx_email.server.hub.subscriptions import update_route
from hx_email.server.push.webhook_deliver import list_deliveries, ping, redeliver
from hx_email.server.push.webhook_feed import FEEDER

PREFIX: str = "/router/subscriptions/{route_id}"


def register_webhook_routes(router: APIRouter, settings: Settings) -> None:
    @router.get(f"{PREFIX}/deliveries")
    def deliveries(
        route_id: int,
        limit: int = Query(default=20, ge=1, le=100),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user_id: int = caller_user_id(settings, authorization, SUBSCRIPTIONS)
        return list_deliveries(settings, user_id, route_id, limit)

    @router.post(f"{PREFIX}/deliveries/{{delivery_id}}/redeliver")
    def redeliver_batch(
        route_id: int, delivery_id: str, authorization: Annotated[str | None, Header()] = None
    ) -> dict[str, object]:
        result: dict[str, object] = redeliver(
            settings, caller_user_id(settings, authorization, SUBSCRIPTIONS), route_id, delivery_id
        )
        DISPATCHER.wake(settings)
        return result

    @router.post(f"{PREFIX}/webhook/ping")
    def ping_receiver(
        route_id: int, authorization: Annotated[str | None, Header()] = None
    ) -> dict[str, object]:
        return ping(settings, caller_user_id(settings, authorization, SUBSCRIPTIONS), route_id)

    @router.post(f"{PREFIX}/webhook/rotate")
    def rotate_secret(
        route_id: int, authorization: Annotated[str | None, Header()] = None
    ) -> dict[str, object]:
        result: dict[str, object] = update_route(
            settings,
            caller_user_id(settings, authorization, SUBSCRIPTIONS),
            route_id,
            rotate_secret=True,
        )
        FEEDER.reload(settings)
        return result
