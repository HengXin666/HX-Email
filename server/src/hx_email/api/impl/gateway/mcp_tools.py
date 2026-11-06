"""MCP tool catalogue of ``hx-router`` (docs/messaging-router.md section 5).

Schemas are plain JSON Schema dicts with ``additionalProperties: false``; ``call_tool``
validates required keys and unknown keys, then calls the same ``server/gateway``
functions the REST routes call. Route persistence (route_subscribe and friends) is not
in this round: listening is ``messages_pull`` plus ``events_wait`` on a source prefix.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from hx_email.config import Settings
from hx_email.server.gateway.catalog import session_select, sessions_list, sources_list
from hx_email.server.gateway.listen import pull, wait_messages
from hx_email.server.gateway.sending import delivery_status, send_message
from hx_email.server.router.errors import RouterError, SessionNotFoundError

JsonDict = dict[str, object]
STR: Final[JsonDict] = {"type": "string"}
INT: Final[JsonDict] = {"type": "integer"}
DIRECTION: Final[JsonDict] = {"type": "string", "enum": ["inbound", "outbound", "both"]}


def schema(properties: JsonDict, required: list[str]) -> JsonDict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


TOOLS: Final[list[JsonDict]] = [
    {
        "name": "sources_list",
        "description": "列出可用平台账号实例 (QQ 号 / GitHub App) 及在线与出站状态",
        "inputSchema": schema({"platform": {"type": "string", "enum": ["qq", "github"]}}, []),
    },
    {
        "name": "sessions_list",
        "description": "列出某个账号实例下可监听与发送的会话 (QQ 好友/群, GitHub 线程)",
        "inputSchema": schema(
            {"instance_id": INT, "session_type": STR, "query": STR, "limit": INT},
            ["instance_id"],
        ),
    },
    {
        "name": "session_select",
        "description": "选定会话, 返回元数据, 起始 cursor 与限流参数; 服务端不保存选定状态",
        "inputSchema": schema(
            {"session": STR, "from": {"type": "string", "enum": ["now", "earliest"]}}, ["session"]
        ),
    },
    {
        "name": "messages_pull",
        "description": "按 cursor 读取会话或地址前缀 (如 qq:3:group:) 的增量消息, 同步只读",
        "inputSchema": schema(
            {
                "source": STR,
                "cursor": STR,
                "limit": INT,
                "direction": DIRECTION,
                "include_raw": {"type": "boolean"},
            },
            ["source", "cursor"],
        ),
    },
    {
        "name": "events_wait",
        "description": "长轮询监听: 阻塞到 source 在 cursor 之后有新消息或超时 (<=55 秒)",
        "inputSchema": schema(
            {
                "source": STR,
                "cursor": STR,
                "timeout_seconds": INT,
                "limit": INT,
                "direction": DIRECTION,
            },
            ["source", "cursor"],
        ),
    },
    {
        "name": "message_send",
        "description": "向会话发送文本; 经幂等, 整形与熔断, 最多等 wait_seconds 秒拿结果",
        "inputSchema": schema(
            {
                "sink": STR,
                "text": {"type": "string", "minLength": 1, "maxLength": 4000},
                "title": STR,
                "reply_to": STR,
                "idempotency_key": {"type": "string", "minLength": 8, "maxLength": 64},
                "wait_seconds": {"type": "number", "minimum": 0, "maximum": 5},
            },
            ["sink", "text", "idempotency_key"],
        ),
    },
    {
        "name": "delivery_status",
        "description": "查询一次发送的状态: 按 delivery_id, 或按 idempotency_key 加 sink",
        "inputSchema": schema({"delivery_id": STR, "idempotency_key": STR, "sink": STR}, []),
    },
]
TOOL_NAMES: Final[frozenset[str]] = frozenset(str(tool["name"]) for tool in TOOLS)


class ToolInputError(ValueError):
    """Arguments do not match the tool's input schema."""


def check_arguments(name: str, arguments: JsonDict) -> None:
    tool: JsonDict = next(item for item in TOOLS if item["name"] == name)
    spec: object = tool["inputSchema"]
    if not isinstance(spec, dict):  # pragma: no cover - static table
        return
    allowed: object = spec["properties"]
    required: object = spec["required"]
    extra: list[str] = [
        key for key in arguments if isinstance(allowed, dict) and key not in allowed
    ]
    if extra:
        raise ToolInputError(f"unknown arguments: {', '.join(extra)}")
    missing: list[str] = [
        key for key in (required if isinstance(required, list) else []) if key not in arguments
    ]
    if missing:
        raise ToolInputError(f"missing arguments: {', '.join(missing)}")


def text_arg(arguments: JsonDict, key: str, default: str = "") -> str:
    value: object = arguments.get(key, default)
    return str(value) if value is not None else default


def int_arg(arguments: JsonDict, key: str, default: int) -> int:
    value: object = arguments.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ToolInputError(f"{key} must be a number")
    try:
        return int(value)
    except ValueError as error:
        raise ToolInputError(f"{key} must be a number") from error


def handlers(settings: Settings, user_id: int) -> dict[str, Callable[[JsonDict], JsonDict]]:
    def delivery(args: JsonDict) -> JsonDict:
        found: JsonDict | None = delivery_status(
            settings,
            user_id,
            delivery_id=text_arg(args, "delivery_id"),
            idempotency_key=text_arg(args, "idempotency_key"),
            sink=text_arg(args, "sink"),
        )
        if found is None:
            raise SessionNotFoundError("delivery not found")
        return found

    return {
        "sources_list": lambda a: sources_list(settings, user_id, text_arg(a, "platform")),
        "sessions_list": lambda a: sessions_list(
            settings,
            user_id,
            int_arg(a, "instance_id", 0),
            session_type=text_arg(a, "session_type"),
            query=text_arg(a, "query"),
            limit=int_arg(a, "limit", 50),
        ),
        "session_select": lambda a: session_select(
            settings, user_id, text_arg(a, "session"), text_arg(a, "from", "now")
        ),
        "messages_pull": lambda a: pull(
            settings,
            user_id,
            text_arg(a, "source"),
            text_arg(a, "cursor"),
            limit=int_arg(a, "limit", 50),
            direction=text_arg(a, "direction", "inbound"),
            include_raw=bool(a.get("include_raw", False)),
        ),
        "events_wait": lambda a: wait_messages(
            settings,
            user_id,
            text_arg(a, "source"),
            text_arg(a, "cursor"),
            timeout_seconds=float(int_arg(a, "timeout_seconds", 25)),
            limit=int_arg(a, "limit", 20),
            direction=text_arg(a, "direction", "inbound"),
        ),
        "message_send": lambda a: send_message(
            settings,
            user_id,
            text_arg(a, "sink"),
            text_arg(a, "text"),
            text_arg(a, "idempotency_key"),
            title=text_arg(a, "title"),
            reply_to=text_arg(a, "reply_to"),
            wait_seconds=float(a.get("wait_seconds", 5.0) or 0.0),
        ),
        "delivery_status": delivery,
    }


def call_tool(settings: Settings, user_id: int, name: str, arguments: JsonDict) -> JsonDict:
    """Run one tool; raises ToolInputError or RouterError for the caller to wrap."""
    if name not in TOOL_NAMES:
        raise ToolInputError(f"unknown tool: {name}")
    check_arguments(name, arguments)
    return handlers(settings, user_id)[name](arguments)


__all__ = ["TOOLS", "RouterError", "ToolInputError", "call_tool"]
