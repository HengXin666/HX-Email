"""JSON-RPC methods of ``hx-router`` for one authenticated caller and session.

``initialize`` is handled by the transport (it mints the session); everything else
lands here: ``ping``, ``tools/list`` (only tools the key's scopes allow),
``tools/call`` (scope checked, sync tools in the thread pool, hub tools awaited),
and the ``resources/*`` family. A missing scope is the JSON-RPC error
``INSUFFICIENT_SCOPE`` with ``data.code = "insufficient_scope"``.
"""

from __future__ import annotations

import json
from typing import Final

import anyio
from fastapi.concurrency import run_in_threadpool

from hx_email.api.impl.gateway.auth import Caller
from hx_email.api.impl.gateway.mcp_tools import TOOLS, ToolInputError, call_tool
from hx_email.api.impl.mcp.output_schemas import with_output_schemas
from hx_email.api.impl.mcp.session_table import McpSession
from hx_email.api.impl.mcp_resources.catalog import (
    TEMPLATES,
    ResourceNotFoundError,
    list_resources,
    read_resource,
)
from hx_email.api.impl.mcp_resources.watch import WatchError, matcher_of, subscribe, unsubscribe
from hx_email.api.impl.subscriptions.mcp_subscription_tools import (
    HUB_TOOL_NAMES,
    SUBSCRIPTION_TOOLS,
    call_hub_tool,
)
from hx_email.config import Settings
from hx_email.server.access.scopes import (
    ACTIONS,
    READ,
    RESOURCES_SUBSCRIBE,
    SEND,
    SUBSCRIPTIONS,
    granted,
)
from hx_email.server.router.errors import InsufficientScopeError, RouterError

JsonDict = dict[str, object]
INVALID_PARAMS: Final[int] = -32602
METHOD_NOT_FOUND: Final[int] = -32601
RESOURCE_NOT_FOUND: Final[int] = -32002
INSUFFICIENT_SCOPE: Final[int] = -32003
ALL_TOOLS: Final[list[JsonDict]] = with_output_schemas([*TOOLS, *SUBSCRIPTION_TOOLS])
TOOL_SCOPES: Final[dict[str, str]] = {
    "message_send": SEND,
    "action_invoke": ACTIONS,
    **{str(tool["name"]): SUBSCRIPTIONS for tool in SUBSCRIPTION_TOOLS},
}
METHOD_SCOPES: Final[dict[str, str]] = {
    "resources/list": READ,
    "resources/templates/list": READ,
    "resources/read": READ,
    "resources/subscribe": RESOURCES_SUBSCRIBE,
    "resources/unsubscribe": RESOURCES_SUBSCRIBE,
}


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: JsonDict | None = None) -> None:
        super().__init__(message)
        self.code: int = code
        self.message: str = message
        self.data: JsonDict | None = data


def rpc_error(
    request_id: object, code: int, message: str, data: JsonDict | None = None
) -> JsonDict:
    error: JsonDict = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def rpc_result(request_id: object, result: JsonDict) -> JsonDict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def tool_result(payload: JsonDict, is_error: bool = False) -> JsonDict:
    text: JsonDict = {"type": "text", "text": json.dumps(payload, ensure_ascii=False)}
    if is_error:
        return {"content": [text], "isError": True}
    return {"content": [text], "structuredContent": payload, "isError": False}


def scope_of_tool(name: str) -> str:
    return TOOL_SCOPES.get(name, READ)


def check(caller: Caller, scope: str) -> None:
    if not granted(caller.scopes, scope):
        raise RpcError(
            INSUFFICIENT_SCOPE,
            f"API key lacks scope {scope}",
            InsufficientScopeError(scope).to_dict(),
        )


def visible_tools(caller: Caller) -> list[JsonDict]:
    return [tool for tool in ALL_TOOLS if granted(caller.scopes, scope_of_tool(str(tool["name"])))]


async def call_named_tool(settings: Settings, caller: Caller, params: JsonDict) -> JsonDict:
    name: str = str(params.get("name") or "")
    arguments: object = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise RpcError(INVALID_PARAMS, "arguments must be an object")
    if name in {str(tool["name"]) for tool in ALL_TOOLS}:
        check(caller, scope_of_tool(name))
    try:
        payload: JsonDict = (
            await call_hub_tool(settings, caller.user_id, name, arguments)
            if name in HUB_TOOL_NAMES
            else await run_in_threadpool(call_tool, settings, caller.user_id, name, arguments)
        )
    except ToolInputError as error:
        raise RpcError(INVALID_PARAMS, str(error)) from error
    except RouterError as error:
        return tool_result(error.to_dict(), is_error=True)
    return tool_result(payload)


def uri_of(params: JsonDict) -> str:
    uri: object = params.get("uri")
    if not isinstance(uri, str) or not uri:
        raise RpcError(INVALID_PARAMS, "uri is required")
    return uri


async def resource_method(
    settings: Settings, caller: Caller, session: McpSession, method: str, params: JsonDict
) -> JsonDict:
    if method == "resources/templates/list":
        return {"resourceTemplates": TEMPLATES}
    if method == "resources/list":
        cursor: str = str(params.get("cursor") or "")
        return await anyio.to_thread.run_sync(
            list_resources, settings, caller.user_id, caller.scopes, cursor
        )
    uri: str = uri_of(params)
    if method == "resources/read":
        return await anyio.to_thread.run_sync(
            read_resource, settings, caller.user_id, caller.scopes, uri
        )
    if method == "resources/unsubscribe":
        unsubscribe(session, uri)
        return {}
    check(caller, READ)
    matcher = await anyio.to_thread.run_sync(
        matcher_of, settings, caller.user_id, caller.scopes, uri
    )
    subscribe(session, uri, matcher)
    return {}


# 每个方法先按 scope 判权再执行; tools/list 只列出该 key 有权调用的工具
async def dispatch(
    settings: Settings, caller: Caller, session: McpSession, method: str, params: JsonDict
) -> JsonDict:
    """Result object of one request; raises ``RpcError`` for JSON-RPC errors."""
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": visible_tools(caller)}
    if method == "tools/call":
        return await call_named_tool(settings, caller, params)
    if method in METHOD_SCOPES:
        check(caller, METHOD_SCOPES[method])
        try:
            return await resource_method(settings, caller, session, method, params)
        except ResourceNotFoundError as error:
            raise RpcError(RESOURCE_NOT_FOUND, str(error), {"uri": params.get("uri")}) from error
        except InsufficientScopeError as error:
            raise RpcError(INSUFFICIENT_SCOPE, error.message, error.to_dict()) from error
        except (WatchError, ValueError) as error:
            raise RpcError(INVALID_PARAMS, str(error)) from error
        except RouterError as error:
            raise RpcError(INVALID_PARAMS, error.message, error.to_dict()) from error
    raise RpcError(METHOD_NOT_FOUND, f"method not found: {method}")
