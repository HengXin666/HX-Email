"""Minimal MCP server ``hx-router`` over Streamable HTTP at ``POST /mcp``.

Stateless JSON-RPC 2.0: every POST carries one request (or a batch) and gets a JSON
response; notifications get 202. No session table, no SSE channel kept open, no SDK:
the official ``mcp`` package would add a dependency tree and an anyio task group per
session for the six methods we need. Listening is the ``events_wait`` tool, which
blocks on the gateway's condition variable inside the thread pool.

Auth: ``Authorization: Bearer <hxr_ router key | console session>`` on every request.
Tool failures come back as ``result.isError=true`` with ``{code, message, retryable}``.
"""

from __future__ import annotations

import json
from typing import Annotated, Final

from fastapi import FastAPI, Header, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

from hx_email.api.impl.gateway.auth import caller_user_id
from hx_email.api.impl.gateway.mcp_tools import TOOLS, ToolInputError, call_tool
from hx_email.config import Settings
from hx_email.server.router.errors import RouterError

PROTOCOL_VERSION: Final[str] = "2025-03-26"
SERVER_INFO: Final[dict[str, str]] = {"name": "hx-router", "version": "1.0.0"}
PARSE_ERROR: Final[int] = -32700
INVALID_REQUEST: Final[int] = -32600
METHOD_NOT_FOUND: Final[int] = -32601
INVALID_PARAMS: Final[int] = -32602

JsonDict = dict[str, object]


def rpc_error(request_id: object, code: int, message: str) -> JsonDict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def rpc_result(request_id: object, result: JsonDict) -> JsonDict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def tool_result(payload: JsonDict, is_error: bool = False) -> JsonDict:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
        "isError": is_error,
    }


def handle_one(settings: Settings, user_id: int, message: object) -> JsonDict | None:
    """One JSON-RPC message; None for notifications (no response body)."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return rpc_error(None, INVALID_REQUEST, "expected a JSON-RPC 2.0 object")
    method: str = str(message.get("method") or "")
    request_id: object = message.get("id")
    if "id" not in message:
        return None
    params: object = message.get("params") or {}
    if not isinstance(params, dict):
        return rpc_error(request_id, INVALID_PARAMS, "params must be an object")
    if method == "initialize":
        return rpc_result(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
                "instructions": (
                    "统一消息路由: capabilities_list 看平台能力, sources_list -> sessions_list -> "
                    "session_select 拿 cursor, "
                    "然后 messages_pull / events_wait 监听, message_send 发送."
                ),
            },
        )
    if method == "ping":
        return rpc_result(request_id, {})
    if method == "tools/list":
        return rpc_result(request_id, {"tools": TOOLS})
    if method != "tools/call":
        return rpc_error(request_id, METHOD_NOT_FOUND, f"method not found: {method}")
    arguments: object = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        return rpc_error(request_id, INVALID_PARAMS, "arguments must be an object")
    try:
        payload: JsonDict = call_tool(settings, user_id, str(params.get("name") or ""), arguments)
    except ToolInputError as error:
        return rpc_error(request_id, INVALID_PARAMS, str(error))
    except RouterError as error:
        return rpc_result(request_id, tool_result(error.to_dict(), is_error=True))
    return rpc_result(request_id, tool_result(payload))


# MCP 用无状态 JSON-RPC 自实现而不是官方 SDK: 只要 6 个方法, 不想为它常驻会话表与任务组
def register_mcp_route(app: FastAPI, settings: Settings) -> None:
    @app.post("/mcp", response_model=None)
    async def mcp_endpoint(
        request: Request, authorization: Annotated[str | None, Header()] = None
    ) -> Response:
        user_id: int = caller_user_id(settings, authorization)
        try:
            body: object = json.loads(await request.body())
        except ValueError:
            return JSONResponse(rpc_error(None, PARSE_ERROR, "invalid JSON"), status_code=400)
        messages: list[object] = body if isinstance(body, list) else [body]
        replies: list[JsonDict] = []
        for message in messages:
            reply: JsonDict | None = await run_in_threadpool(handle_one, settings, user_id, message)
            if reply is not None:
                replies.append(reply)
        if not replies:
            return Response(status_code=202)
        return JSONResponse(replies if isinstance(body, list) else replies[0])

    @app.get("/mcp", response_model=None)
    def mcp_get() -> Response:
        return Response(status_code=405, headers={"Allow": "POST"})
