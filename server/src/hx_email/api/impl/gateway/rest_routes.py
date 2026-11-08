"""REST face of the router gateway under ``/api/v1/router`` (docs/messaging-router.md 6).

Each route is a thin call into ``server/gateway``; MCP calls the very same functions,
so REST and MCP cannot drift apart. Sync routes run in FastAPI's thread pool, which is
what lets ``wait`` block on a condition variable without stalling the event loop.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import AsyncIterator
from functools import partial
from typing import Annotated, Literal

import anyio
from fastapi import APIRouter, FastAPI, Header, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from hx_email.api.impl.gateway.admin_routes import register_gateway_admin_routes
from hx_email.api.impl.gateway.auth import caller_user_id
from hx_email.api.impl.gateway.mcp_server import register_mcp_route
from hx_email.api.impl.router.errors import install_router_error_handler
from hx_email.config import Settings
from hx_email.server.gateway.catalog import (
    capabilities_list,
    session_select,
    sessions_list,
    sources_list,
)
from hx_email.server.gateway.impl.dispatch import DISPATCHER, seconds_until_next
from hx_email.server.gateway.listen import pull, wait_messages
from hx_email.server.gateway.sending import delivery_status, send_message
from hx_email.server.router.impl.outbox_admin import recover_after_restart

LOGGER: logging.Logger = logging.getLogger("hx_email.gateway.rest")

PREFIX: str = "/router"
Direction = Literal["inbound", "outbound", "both"]
HEARTBEAT_SECONDS: float = 25.0


class SelectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session: str
    start: Literal["now", "earliest"] = Field(default="now", alias="from")


class SendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sink: str
    text: str = Field(min_length=1, max_length=4000)
    title: str = ""
    reply_to: str = ""
    idempotency_key: str = Field(default="", max_length=64, pattern=r"^[A-Za-z0-9_.:-]*$")
    wait_seconds: float = Field(default=5.0, ge=0, le=5)


def sse_frame(payload: dict[str, object], frame_id: str = "") -> str:
    head: str = f"id: {frame_id}\n" if frame_id else ""
    return f"{head}data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# REST 与 MCP 调同一组 server/gateway 函数, 两个入口不会各自漂移
# 决策记录: .agents/notes/implemented/feature/2026-11-06-router-gateway-facade.md
def register_gateway(app: FastAPI, api: APIRouter, settings: Settings) -> None:
    """Mount REST under ``/api/v1/router``, MCP at ``/mcp``, and the startup recovery."""
    register_gateway_rest_routes(api, settings)
    register_gateway_admin_routes(api, settings)
    register_mcp_route(app, settings)
    install_router_error_handler(app)

    @app.on_event("startup")
    def recover_outbox() -> None:
        try:
            recover_after_restart(settings)
            pending: float | None = seconds_until_next(settings)
        except sqlite3.OperationalError as error:
            # 未迁移的库 (只读健康检查, 测试夹具) 没有 router_outbox, 恢复无事可做
            LOGGER.info("skip outbox recovery: %s", error)
            return
        if pending is not None:
            DISPATCHER.wake(settings)


def register_gateway_rest_routes(router: APIRouter, settings: Settings) -> None:
    @router.get(f"{PREFIX}/capabilities")
    def capabilities(
        platform: str = "", authorization: Annotated[str | None, Header()] = None
    ) -> dict[str, object]:
        caller_user_id(settings, authorization)
        return capabilities_list(platform)

    @router.get(f"{PREFIX}/sources")
    def sources(
        platform: str = "", authorization: Annotated[str | None, Header()] = None
    ) -> dict[str, object]:
        return sources_list(settings, caller_user_id(settings, authorization), platform)

    @router.get(f"{PREFIX}/instances/{{instance_id}}/sessions")
    def sessions(
        instance_id: int,
        session_type: str = "",
        query: str = "",
        limit: int = Query(default=50, ge=1, le=200),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user_id: int = caller_user_id(settings, authorization)
        return sessions_list(
            settings, user_id, instance_id, session_type=session_type, query=query, limit=limit
        )

    @router.post(f"{PREFIX}/sessions/select")
    def select(
        payload: SelectRequest, authorization: Annotated[str | None, Header()] = None
    ) -> dict[str, object]:
        user_id: int = caller_user_id(settings, authorization)
        return session_select(settings, user_id, payload.session, payload.start)

    @router.get(f"{PREFIX}/messages")
    def messages(
        source: str,
        cursor: str = "",
        limit: int = Query(default=50, ge=1, le=200),
        direction: Direction = "inbound",
        include_raw: bool = False,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user_id: int = caller_user_id(settings, authorization)
        return pull(
            settings,
            user_id,
            source,
            cursor,
            limit=limit,
            direction=direction,
            include_raw=include_raw,
        )

    @router.post(f"{PREFIX}/messages")
    def send(
        payload: SendRequest,
        response: Response,
        authorization: Annotated[str | None, Header()] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict[str, object]:
        user_id: int = caller_user_id(settings, authorization)
        result: dict[str, object] = send_message(
            settings,
            user_id,
            payload.sink,
            payload.text,
            payload.idempotency_key or (idempotency_key or ""),
            title=payload.title,
            reply_to=payload.reply_to,
            wait_seconds=payload.wait_seconds,
        )
        if result["status"] in ("queued", "sending", "held"):
            response.status_code = status.HTTP_202_ACCEPTED
        return result

    @router.get(f"{PREFIX}/deliveries/{{delivery_id}}")
    def delivery(
        delivery_id: str, authorization: Annotated[str | None, Header()] = None
    ) -> dict[str, object]:
        user_id: int = caller_user_id(settings, authorization)
        found = delivery_status(settings, user_id, delivery_id=delivery_id)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery not found")
        return found

    @router.get(f"{PREFIX}/deliveries")
    def delivery_by_key(
        idempotency_key: str, sink: str, authorization: Annotated[str | None, Header()] = None
    ) -> dict[str, object]:
        user_id: int = caller_user_id(settings, authorization)
        found = delivery_status(settings, user_id, idempotency_key=idempotency_key, sink=sink)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery not found")
        return found

    @router.get(f"{PREFIX}/wait")
    def wait(
        source: str,
        cursor: str = "",
        timeout_seconds: int = Query(default=25, ge=1, le=55),
        limit: int = Query(default=20, ge=1, le=50),
        direction: Direction = "inbound",
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user_id: int = caller_user_id(settings, authorization)
        return wait_messages(
            settings,
            user_id,
            source,
            cursor,
            timeout_seconds=timeout_seconds,
            limit=limit,
            direction=direction,
        )

    @router.get(f"{PREFIX}/stream")
    def stream(
        source: str,
        cursor: str = "",
        authorization: Annotated[str | None, Header()] = None,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> StreamingResponse:
        user_id: int = caller_user_id(settings, authorization)
        start: str = last_event_id or cursor
        pull(settings, user_id, source, start, limit=1)  # validate scope before streaming

        async def frames() -> AsyncIterator[str]:
            position: str = start
            while True:
                page: dict[str, object] = await anyio.to_thread.run_sync(
                    partial(
                        wait_messages,
                        settings,
                        user_id,
                        source,
                        position,
                        timeout_seconds=HEARTBEAT_SECONDS,
                    )
                )
                position = str(page["next_cursor"])
                items: object = page["messages"]
                if isinstance(items, list) and items:
                    for item in items:
                        yield sse_frame(item, str(item.get("cursor", "")))
                else:
                    yield ":\n\n"

        return StreamingResponse(frames(), media_type="text/event-stream")
