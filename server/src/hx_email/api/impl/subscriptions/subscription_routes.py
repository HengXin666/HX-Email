"""REST face of persistent subscriptions under ``/api/v1/router/subscriptions``.

CRUD is plain sync (short SQLite calls in the thread pool). The two listening routes,
``/events`` (long-poll) and ``/stream`` (SSE), are ``async def`` and wait on the hub,
so an idle consumer holds no worker thread. MCP calls the same ``server/hub`` functions.
"""

from __future__ import annotations

from typing import Annotated, Literal

import anyio
from fastapi import APIRouter, Header, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from hx_email.api.impl.gateway.auth import caller_user_id
from hx_email.config import Settings
from hx_email.server.hub.bus import BUS
from hx_email.server.hub.consume import route_stream, wait_route
from hx_email.server.hub.subscriptions import (
    Route,
    ack_route,
    create_route,
    delete_route,
    get_route,
    list_routes,
    update_route,
)
from hx_email.server.router.errors import RouteInvalidError

PREFIX: str = "/router/subscriptions"
SSE_HEADERS: dict[str, str] = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class FilterBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    direction: Literal["inbound", "outbound", "both"] = "inbound"
    kinds: list[str] = Field(default_factory=list, max_length=16)
    exclude_self: bool = True
    mention_self: bool = False
    contains: str = Field(default="", max_length=200)


class CreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    source: str = Field(min_length=3, max_length=300)
    name: str = Field(default="", max_length=64)
    filter: FilterBody = Field(default_factory=FilterBody)
    start: Literal["now", "earliest"] = Field(default="now", alias="from")


class UpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=64)
    status: Literal["active", "paused"] | None = None
    filter: FilterBody | None = None


class AckBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cursor: str = Field(min_length=1, max_length=64)


# 订阅持久化在 router_routes, 监听路由是 async 的, 等待期间不占线程池
# 决策记录: .agents/notes/implemented/feature/2026-11-08-router-hub-subscriptions.md
def register_subscription_routes(router: APIRouter, settings: Settings) -> None:
    """Mount subscription CRUD, long-poll, SSE and hub stats."""

    @router.get("/router/hub")
    def hub_stats(authorization: Annotated[str | None, Header()] = None) -> dict[str, object]:
        caller_user_id(settings, authorization)
        return {"waiting": BUS.waiting(), "published": BUS.published}

    @router.post(PREFIX, status_code=status.HTTP_201_CREATED)
    def create(
        payload: CreateBody, authorization: Annotated[str | None, Header()] = None
    ) -> dict[str, object]:
        return create_route(
            settings,
            caller_user_id(settings, authorization),
            source=payload.source,
            name=payload.name,
            filter_data=payload.filter.model_dump(),
            start=payload.start,
        )

    @router.get(PREFIX)
    def listing(authorization: Annotated[str | None, Header()] = None) -> dict[str, object]:
        return list_routes(settings, caller_user_id(settings, authorization))

    @router.get(f"{PREFIX}/{{route_id}}")
    def detail(
        route_id: int, authorization: Annotated[str | None, Header()] = None
    ) -> dict[str, object]:
        return get_route(settings, caller_user_id(settings, authorization), route_id).to_dict()

    @router.patch(f"{PREFIX}/{{route_id}}")
    def update(
        route_id: int,
        payload: UpdateBody,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        return update_route(
            settings,
            caller_user_id(settings, authorization),
            route_id,
            name=payload.name,
            status=payload.status,
            filter_data=payload.filter.model_dump() if payload.filter else None,
        )

    @router.delete(f"{PREFIX}/{{route_id}}")
    def remove(
        route_id: int, authorization: Annotated[str | None, Header()] = None
    ) -> dict[str, object]:
        return delete_route(settings, caller_user_id(settings, authorization), route_id)

    @router.post(f"{PREFIX}/{{route_id}}/ack")
    def ack(
        route_id: int, payload: AckBody, authorization: Annotated[str | None, Header()] = None
    ) -> dict[str, object]:
        return ack_route(
            settings, caller_user_id(settings, authorization), route_id, payload.cursor
        )

    @router.get(f"{PREFIX}/{{route_id}}/events")
    async def events(
        route_id: int,
        response: Response,
        cursor: str = "",
        timeout_seconds: int = Query(default=25, ge=0, le=55),
        limit: int = Query(default=20, ge=1, le=100),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user_id: int = await anyio.to_thread.run_sync(caller_user_id, settings, authorization)
        response.headers["Cache-Control"] = "no-store"
        return await wait_route(
            settings,
            user_id,
            route_id,
            cursor=cursor,
            timeout_seconds=float(timeout_seconds),
            limit=limit,
        )

    @router.get(f"{PREFIX}/{{route_id}}/stream")
    async def stream(
        route_id: int,
        auto_ack: bool = False,
        cursor: str = "",
        authorization: Annotated[str | None, Header()] = None,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> StreamingResponse:
        user_id: int = await anyio.to_thread.run_sync(caller_user_id, settings, authorization)
        route: Route = await anyio.to_thread.run_sync(get_route, settings, user_id, route_id)
        if route.status != "active":
            raise RouteInvalidError(f"subscription {route_id} is paused")
        frames = route_stream(settings, user_id, route, last_event_id or cursor, auto_ack)
        return StreamingResponse(frames, media_type="text/event-stream", headers=SSE_HEADERS)
