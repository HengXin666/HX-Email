"""HTTP side of the MCP Streamable HTTP transport: GET stream, DELETE, session headers.

``GET /mcp`` (``Accept: text/event-stream`` plus ``Mcp-Session-Id``) opens the
server-to-client SSE stream of a session: it replays ring frames newer than
``Last-Event-ID``, then sleeps on the session's wake event, sending a comment
heartbeat every ``HEARTBEAT_SECONDS``. The stream holds no thread while idle. When the
client goes away Starlette cancels the generator and ``finally`` detaches the slot.

``DELETE /mcp`` ends the session (stream closed, hub waiters dropped).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated, Final

import anyio
from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse, Response, StreamingResponse

from hx_email.api.impl.gateway.auth import Caller, resolve_caller
from hx_email.api.impl.mcp.session_table import TABLE, McpSession, StreamSlot
from hx_email.config import Settings
from hx_email.server.access.scopes import MCP, require_scope

PROTOCOL_VERSIONS: Final[tuple[str, ...]] = ("2025-06-18", "2025-03-26")
LATEST_PROTOCOL: Final[str] = PROTOCOL_VERSIONS[0]
SESSION_HEADER: Final[str] = "Mcp-Session-Id"
HEARTBEAT_SECONDS: float = 15.0
SESSION_REQUIRED: Final[int] = -32000


def http_error(status_code: int, message: str) -> JSONResponse:
    body: dict[str, object] = {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": SESSION_REQUIRED, "message": message},
    }
    return JSONResponse(body, status_code=status_code)


def protocol_problem(version: str | None) -> JSONResponse | None:
    """400 for an ``MCP-Protocol-Version`` header we do not speak; absent is fine."""
    if version is None or version in PROTOCOL_VERSIONS:
        return None
    return http_error(400, f"unsupported MCP-Protocol-Version: {version}")


async def mcp_caller(settings: Settings, authorization: str | None) -> Caller:
    """Authenticated caller holding the ``mcp`` scope (otherwise 401 / 403)."""
    caller: Caller = await anyio.to_thread.run_sync(resolve_caller, settings, authorization)
    require_scope(caller.scopes, MCP)
    return caller


def lookup(caller: Caller, session_id: str | None) -> McpSession | JSONResponse:
    """Session for a non-initialize request: 400 without the header, 404 if unknown."""
    if not session_id:
        return http_error(400, f"missing {SESSION_HEADER}; call initialize first")
    session: McpSession | None = TABLE.get(session_id, caller.principal)
    if session is None:
        return http_error(404, "session not found or expired; initialize again")
    return session


def resume_point(last_event_id: str | None) -> int | None:
    text: str = (last_event_id or "").strip()
    return int(text) if text.isascii() and text.isdigit() else None


# GET 流只保留一条: 新流顶替旧流, 每条通知只走一条流; 断线后按 Last-Event-ID 从有界环形缓冲补发
async def session_frames(session: McpSession, resume: int | None) -> AsyncIterator[str]:
    """SSE text for one GET stream; ends when replaced, deleted or expired."""
    slot = StreamSlot(asyncio.get_running_loop(), asyncio.Event())
    sent: int = session.attach(slot, resume)
    try:
        yield ": stream open\n\n"
        while not slot.closed:
            slot.wake.clear()
            for seq, frame in session.take_after(sent):
                yield frame
                sent = seq
            if slot.closed:
                break
            try:
                await asyncio.wait_for(slot.wake.wait(), timeout=HEARTBEAT_SECONDS)
            except TimeoutError:
                session.touch()
                yield ": ping\n\n"
    finally:
        session.detach(slot)


def register_mcp_session_routes(app: FastAPI, settings: Settings) -> None:
    @app.get("/mcp", response_model=None)
    async def mcp_stream(
        authorization: Annotated[str | None, Header()] = None,
        accept: Annotated[str | None, Header()] = None,
        mcp_session_id: Annotated[str | None, Header(alias=SESSION_HEADER)] = None,
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
        protocol: Annotated[str | None, Header(alias="MCP-Protocol-Version")] = None,
    ) -> Response:
        caller: Caller = await mcp_caller(settings, authorization)
        if "text/event-stream" not in (accept or ""):
            return Response(status_code=406, content="Accept must include text/event-stream")
        problem: JSONResponse | None = protocol_problem(protocol)
        if problem is not None:
            return problem
        found: McpSession | JSONResponse = lookup(caller, mcp_session_id)
        if isinstance(found, JSONResponse):
            return found
        return StreamingResponse(
            session_frames(found, resume_point(last_event_id)),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                SESSION_HEADER: found.session_id,
            },
        )

    @app.delete("/mcp", response_model=None)
    async def mcp_end(
        authorization: Annotated[str | None, Header()] = None,
        mcp_session_id: Annotated[str | None, Header(alias=SESSION_HEADER)] = None,
    ) -> Response:
        caller: Caller = await mcp_caller(settings, authorization)
        found: McpSession | JSONResponse = lookup(caller, mcp_session_id)
        if isinstance(found, JSONResponse):
            return found
        TABLE.close(found.session_id, caller.principal)
        return Response(status_code=204)
