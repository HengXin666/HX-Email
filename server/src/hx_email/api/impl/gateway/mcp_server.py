"""MCP server ``hx-router`` over Streamable HTTP at ``/mcp`` (POST side).

JSON-RPC 2.0 without the SDK. ``initialize`` mints an ``Mcp-Session-Id`` (returned in
the response header); every later POST must carry it: missing is 400, unknown or
expired is 404. Requests get a JSON response; a body of only notifications or
responses gets 202. ``GET /mcp`` (server-to-client SSE) and ``DELETE /mcp`` live in
``api/impl/mcp/transport.py``; methods in ``api/impl/mcp/methods.py``.

Auth: ``Authorization: Bearer <hxr_ router key | console session>`` on every request,
holding the ``mcp`` scope. Tool failures come back as ``result.isError=true`` with
``{code, message, retryable}``; scope failures as JSON-RPC error -32003.
"""

from __future__ import annotations

import json
from typing import Annotated, Final

import anyio
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, Response

from hx_email.api.impl.gateway.auth import Caller
from hx_email.api.impl.mcp.methods import RpcError, dispatch, rpc_error, rpc_result
from hx_email.api.impl.mcp.session_table import TABLE, McpSession, SessionLimitError
from hx_email.api.impl.mcp.transport import (
    LATEST_PROTOCOL,
    PROTOCOL_VERSIONS,
    SESSION_HEADER,
    http_error,
    lookup,
    mcp_caller,
    protocol_problem,
    register_mcp_session_routes,
)
from hx_email.config import Settings

SERVER_INFO: Final[dict[str, str]] = {"name": "hx-router", "version": "1.1.0"}
PARSE_ERROR: Final[int] = -32700
INVALID_REQUEST: Final[int] = -32600
INVALID_PARAMS: Final[int] = -32602
INSTRUCTIONS: Final[str] = (
    "统一消息路由: capabilities_list 看平台能力, sources_list -> sessions_list -> "
    "session_select 拿 cursor, 然后 messages_pull / events_wait 监听; 要断线续读就 "
    "subscription_create 再 subscription_wait + subscription_ack; message_send 发送. "
    "也可 resources/subscribe 一个 hx://router/... 资源, 经 GET /mcp 的 SSE 收到更新通知."
)

JsonDict = dict[str, object]


def initialize_result(params: JsonDict) -> JsonDict:
    asked: object = params.get("protocolVersion")
    version: str = (
        asked if isinstance(asked, str) and asked in PROTOCOL_VERSIONS else LATEST_PROTOCOL
    )
    return {
        "protocolVersion": version,
        "capabilities": {
            "tools": {"listChanged": False},
            "resources": {"subscribe": True, "listChanged": True},
        },
        "serverInfo": SERVER_INFO,
        "instructions": INSTRUCTIONS,
    }


async def answer(
    settings: Settings, caller: Caller, session: McpSession, message: object
) -> JsonDict | None:
    """One JSON-RPC message; None for notifications and client responses."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return rpc_error(None, INVALID_REQUEST, "expected a JSON-RPC 2.0 object")
    if "id" not in message or "method" not in message:
        return None
    request_id: object = message.get("id")
    method: str = str(message.get("method") or "")
    params: object = message.get("params") or {}
    if not isinstance(params, dict):
        return rpc_error(request_id, INVALID_PARAMS, "params must be an object")
    if method == "initialize":
        return rpc_result(request_id, initialize_result(params))
    try:
        return rpc_result(request_id, await dispatch(settings, caller, session, method, params))
    except RpcError as error:
        return rpc_error(request_id, error.code, error.message, error.data)


def is_initialize(message: object) -> bool:
    return isinstance(message, dict) and message.get("method") == "initialize"


# MCP 仍自实现而不用官方 SDK; 会话表与 GET 流见 api/impl/mcp, 都有上限与过期清理
def register_mcp_route(app: FastAPI, settings: Settings) -> None:
    register_mcp_session_routes(app, settings)

    @app.post("/mcp", response_model=None)
    async def mcp_endpoint(
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        mcp_session_id: Annotated[str | None, Header(alias=SESSION_HEADER)] = None,
        protocol: Annotated[str | None, Header(alias="MCP-Protocol-Version")] = None,
    ) -> Response:
        caller: Caller = await mcp_caller(settings, authorization)
        try:
            body: object = json.loads(await request.body())
        except ValueError:
            return JSONResponse(rpc_error(None, PARSE_ERROR, "invalid JSON"), status_code=400)
        messages: list[object] = body if isinstance(body, list) else [body]
        initializing: object = next((m for m in messages if is_initialize(m)), None)
        found: McpSession | JSONResponse
        if isinstance(initializing, dict):
            params: object = initializing.get("params") or {}
            version: str = str(
                initialize_result(params if isinstance(params, dict) else {})["protocolVersion"]
            )
            try:
                found = await anyio.to_thread.run_sync(
                    TABLE.create, caller.principal, caller.user_id, version
                )
            except SessionLimitError as error:
                return http_error(503, str(error))
        else:
            problem: JSONResponse | None = protocol_problem(protocol)
            if problem is not None:
                return problem
            found = lookup(caller, mcp_session_id)
            if isinstance(found, JSONResponse):
                return found
        replies: list[JsonDict] = []
        for message in messages:
            reply: JsonDict | None = await answer(settings, caller, found, message)
            if reply is not None:
                replies.append(reply)
        headers: dict[str, str] = {SESSION_HEADER: found.session_id}
        if not replies:
            return Response(status_code=202, headers=headers)
        return JSONResponse(replies if isinstance(body, list) else replies[0], headers=headers)

    # 根路径 GET /{filename} (Google 站点验证) 先注册, 会吞掉 GET /mcp; 把 /mcp 路由挪到最前
    first: list[object] = [r for r in app.router.routes if getattr(r, "path", "") == "/mcp"]
    rest: list[object] = [r for r in app.router.routes if getattr(r, "path", "") != "/mcp"]
    app.router.routes[:] = [*first, *rest]  # type: ignore[list-item]
