"""MCP tools that wait on the hub or touch persistent subscriptions.

These run as coroutines in the MCP endpoint instead of the thread pool: ``events_wait``
and ``subscription_wait`` sleep on the hub, and the short CRUD calls hop to a worker
thread only for their SQLite work. Schemas follow ``mcp_tools`` (no extra keys).
"""

from __future__ import annotations

from typing import Final

import anyio

from hx_email.api.impl.gateway.mcp_tools import (
    BOOL,
    DIRECTION,
    INT,
    STR,
    TOOLS,
    JsonDict,
    check_arguments,
    int_arg,
    schema,
    text_arg,
)
from hx_email.config import Settings
from hx_email.server.hub.consume import wait_route, wait_source
from hx_email.server.hub.subscriptions import ack_route, create_route, list_routes
from hx_email.server.push.webhook_feed import FEEDER

FILTER: Final[JsonDict] = {
    "type": "object",
    "properties": {
        "direction": DIRECTION,
        "kinds": {"type": "array", "items": STR},
        "exclude_self": BOOL,
        "mention_self": BOOL,
        "contains": STR,
    },
    "additionalProperties": False,
}
SUBSCRIPTION_TOOLS: Final[list[JsonDict]] = [
    {
        "name": "subscriptions_list",
        "description": "列出持久订阅: 来源, 过滤条件, 已确认位置 ack_cursor 与积压条数",
        "inputSchema": schema({}, []),
    },
    {
        "name": "subscription_create",
        "description": (
            "创建持久订阅: source 是会话或前缀 (如 qq:3/group, github:7/repo/o/r), "
            "重启与断线后从 ack 续读, 不丢消息; delivery=webhook 时服务端把批次签名后 POST 到 "
            "webhook_url, 返回的 webhook_secret 只出现这一次"
        ),
        "inputSchema": schema(
            {
                "source": STR,
                "name": STR,
                "filter": FILTER,
                "from": {"type": "string", "enum": ["now", "earliest"]},
                "delivery": {"type": "string", "enum": ["pull", "webhook"]},
                "webhook_url": STR,
            },
            ["source"],
        ),
    },
    {
        "name": "subscription_wait",
        "description": "按订阅长轮询: 从 cursor (缺省为 ack) 起等到有符合过滤的消息或超时",
        "inputSchema": schema(
            {"subscription_id": INT, "cursor": STR, "timeout_seconds": INT, "limit": INT},
            ["subscription_id"],
        ),
    },
    {
        "name": "subscription_ack",
        "description": "确认处理到 cursor; 只前进不回退, 下次 subscription_wait 从这里继续",
        "inputSchema": schema(
            {"subscription_id": INT, "cursor": STR}, ["subscription_id", "cursor"]
        ),
    },
]
HUB_TOOL_NAMES: Final[frozenset[str]] = frozenset(
    {"events_wait", *(str(tool["name"]) for tool in SUBSCRIPTION_TOOLS)}
)


# 等待类工具在事件循环里 await hub, 不进线程池; 增删查只为 SQLite 借一次工作线程
async def call_hub_tool(
    settings: Settings, user_id: int, name: str, arguments: JsonDict
) -> JsonDict:
    """Run one hub tool; raises ToolInputError or RouterError like ``call_tool``."""
    check_arguments(name, arguments, [*TOOLS, *SUBSCRIPTION_TOOLS])
    timeout: float = float(int_arg(arguments, "timeout_seconds", 25))
    if name == "events_wait":
        return await wait_source(
            settings,
            user_id,
            text_arg(arguments, "source"),
            text_arg(arguments, "cursor"),
            timeout_seconds=timeout,
            limit=int_arg(arguments, "limit", 20),
            direction=text_arg(arguments, "direction", "inbound"),
        )
    if name == "subscription_wait":
        return await wait_route(
            settings,
            user_id,
            int_arg(arguments, "subscription_id", 0),
            cursor=text_arg(arguments, "cursor"),
            timeout_seconds=timeout,
            limit=int_arg(arguments, "limit", 20),
        )
    if name == "subscription_ack":
        return await anyio.to_thread.run_sync(
            ack_route,
            settings,
            user_id,
            int_arg(arguments, "subscription_id", 0),
            text_arg(arguments, "cursor"),
        )
    if name == "subscription_create":

        def create() -> JsonDict:
            return create_route(
                settings,
                user_id,
                source=text_arg(arguments, "source"),
                name=text_arg(arguments, "name"),
                filter_data=arguments.get("filter"),
                start=text_arg(arguments, "from", "now"),
                delivery=text_arg(arguments, "delivery", "pull"),
                webhook_url=text_arg(arguments, "webhook_url") or None,
            )

        created: JsonDict = await anyio.to_thread.run_sync(create)
        await anyio.to_thread.run_sync(FEEDER.reload, settings)
        return created
    return await anyio.to_thread.run_sync(list_routes, settings, user_id)
