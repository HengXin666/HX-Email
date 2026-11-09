"""``outputSchema`` of every ``hx-router`` tool (MCP 2025-06-18).

Each successful ``tools/call`` returns the same payload twice: ``structuredContent``
(validated against the schema below by the tests) and a JSON ``text`` block for
clients older than 2025-06-18. Schemas pin the keys callers rely on and leave room
for additions (no ``additionalProperties: false``), so adding a field is not a
breaking change. Errors (``isError: true``) carry only the text block, because the
error triple does not match the success schema.
"""

from __future__ import annotations

from typing import Final

JsonDict = dict[str, object]
STR: Final[JsonDict] = {"type": "string"}
BOOL: Final[JsonDict] = {"type": "boolean"}
INT: Final[JsonDict] = {"type": "integer"}
LIST: Final[JsonDict] = {"type": "array", "items": {"type": "object"}}


def obj(properties: JsonDict) -> JsonDict:
    return {"type": "object", "properties": properties, "required": sorted(properties)}


PAGE: Final[JsonDict] = {"messages": LIST, "next_cursor": STR, "has_more": BOOL, "gap": BOOL}
DELIVERY: Final[JsonDict] = obj(
    {
        "delivery_id": STR,
        "kind": STR,
        "action": STR,
        "sink": STR,
        "status": STR,
        "deduplicated": BOOL,
        "attempts": INT,
    }
)
ROUTE: Final[JsonDict] = obj(
    {"id": INT, "source": STR, "delivery": STR, "status": STR, "ack_cursor": STR}
)
OUTPUT_SCHEMAS: Final[dict[str, JsonDict]] = {
    "capabilities_list": obj({"contract": INT, "platforms": LIST}),
    "sources_list": obj({"sources": LIST}),
    "sessions_list": obj({"sessions": LIST}),
    "session_select": obj(
        {"session": STR, "cursor": STR, "can_send": BOOL, "limits": {"type": "object"}}
    ),
    "messages_pull": obj(PAGE),
    "events_wait": obj({**PAGE, "timed_out": BOOL}),
    "message_send": DELIVERY,
    "action_invoke": DELIVERY,
    "delivery_status": DELIVERY,
    "subscriptions_list": obj({"subscriptions": LIST}),
    "subscription_create": ROUTE,
    "subscription_wait": obj(
        {**PAGE, "subscription_id": INT, "ack_cursor": STR, "timed_out": BOOL}
    ),
    "subscription_ack": ROUTE,
}


# 输出 schema 只钉住调用方依赖的键, 允许追加字段; 旧客户端仍读 text 块
def with_output_schemas(tools: list[JsonDict]) -> list[JsonDict]:
    """Tool descriptors with ``outputSchema`` attached (copies, the tables stay intact)."""
    return [
        {**tool, "outputSchema": OUTPUT_SCHEMAS[str(tool["name"])]}
        if str(tool["name"]) in OUTPUT_SCHEMAS
        else tool
        for tool in tools
    ]
