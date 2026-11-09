"""MCP resources of ``hx-router``: what exists, how to read it (docs/messaging-router.md 5.4).

Resources hang off domain objects that already exist; nothing new is stored:

- ``hx://router/capabilities``: the contract v2 capability table (static).
- ``hx://router/sources``: the caller's account instances and their outbound state.
- ``hx://router/instances/{instance_id}``: one instance plus its newest cursor.
- ``hx://router/sessions/{session}/messages{?cursor,limit}``: without ``cursor`` the
  newest ``limit`` messages (default 20, max 100); with one, the page after it. The
  session is percent-encoded (``qq%3A3%2Fgroup%2F555``); a raw address also parses.
- ``hx://router/subscriptions/{subscription_id}``: a persistent subscription, its ack
  cursor and backlog (needs the ``subscriptions`` scope).
- ``hx://router/deliveries/{delivery_id}``: one outbound delivery (template only).

``resources/list`` pages with an opaque cursor, ``PAGE_SIZE`` per page; the listing is
built from two indexed queries, never from live platform calls.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Final
from urllib.parse import parse_qs, quote, unquote, urlsplit

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.access.scopes import SUBSCRIPTIONS, granted, require_scope
from hx_email.server.contract.event import event_view
from hx_email.server.gateway.catalog import capabilities_list, sources_list
from hx_email.server.gateway.listen import pull, recent_messages
from hx_email.server.gateway.providers import require_owned
from hx_email.server.gateway.sending import delivery_status
from hx_email.server.hub.subscriptions import get_route
from hx_email.server.router.envelope import parse_session
from hx_email.server.router.errors import RouteNotFoundError, SessionNotFoundError
from hx_email.server.router.impl.reader import latest_cursor

JsonDict = dict[str, object]
ROOT: Final[str] = "hx://router/"
PAGE_SIZE: Final[int] = 50
DEFAULT_RECENT: Final[int] = 20
MAX_RECENT: Final[int] = 100
JSON_TYPE: Final[str] = "application/json"
TEMPLATES: Final[list[JsonDict]] = [
    {
        "uriTemplate": "hx://router/instances/{instance_id}",
        "name": "instance",
        "description": "一个平台账号实例: 在线与出站状态, 最新 cursor",
        "mimeType": JSON_TYPE,
    },
    {
        "uriTemplate": "hx://router/sessions/{session}/messages{?cursor,limit}",
        "name": "session_messages",
        "description": "会话最近 N 条消息 (session 需 URL 编码); 带 cursor 时读其后一页",
        "mimeType": JSON_TYPE,
    },
    {
        "uriTemplate": "hx://router/subscriptions/{subscription_id}",
        "name": "subscription",
        "description": "持久订阅的过滤条件, ack_cursor 与积压",
        "mimeType": JSON_TYPE,
    },
    {
        "uriTemplate": "hx://router/deliveries/{delivery_id}",
        "name": "delivery",
        "description": "一次出站投递的状态",
        "mimeType": JSON_TYPE,
    },
]


class ResourceNotFoundError(Exception):
    """URI is malformed, unknown, or names something the caller does not own."""


def session_uri(session: str) -> str:
    return f"{ROOT}sessions/{quote(session, safe='')}/messages"


def entry(uri: str, name: str, description: str) -> JsonDict:
    return {"uri": uri, "name": name, "description": description, "mimeType": JSON_TYPE}


def all_entries(settings: Settings, user_id: int, scopes: frozenset[str]) -> list[JsonDict]:
    out: list[JsonDict] = [
        entry(f"{ROOT}capabilities", "capabilities", "各平台的地址层级, 事件种类与动作"),
        entry(f"{ROOT}sources", "sources", "可用账号实例及在线与出站状态"),
    ]
    with connect(settings) as connection:
        instances: list[sqlite3.Row] = connection.execute(
            "SELECT id, kind, name FROM messaging_instances WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
        routes: list[sqlite3.Row] = (
            connection.execute(
                "SELECT id, name, source_prefix FROM router_routes WHERE user_id = ? ORDER BY id",
                (user_id,),
            ).fetchall()
            if granted(scopes, SUBSCRIPTIONS)
            else []
        )
    for row in instances:
        out.append(
            entry(f"{ROOT}instances/{row['id']}", f"{row['kind']}:{row['id']}", str(row["name"]))
        )
    for row in routes:
        label: str = str(row["name"] or row["source_prefix"])
        out.append(entry(f"{ROOT}subscriptions/{row['id']}", f"subscription:{row['id']}", label))
    return out


def list_resources(
    settings: Settings, user_id: int, scopes: frozenset[str], cursor: str = ""
) -> JsonDict:
    """One page of ``resources/list``; ``nextCursor`` only when more remain."""
    offset: int = 0
    if cursor:
        if not (cursor.startswith("o") and cursor[1:].isdigit()):
            raise ValueError("invalid cursor")
        offset = int(cursor[1:])
    items: list[JsonDict] = all_entries(settings, user_id, scopes)
    page: JsonDict = {"resources": items[offset : offset + PAGE_SIZE]}
    if offset + PAGE_SIZE < len(items):
        page["nextCursor"] = f"o{offset + PAGE_SIZE}"
    return page


def split_uri(uri: str) -> tuple[list[str], dict[str, str]]:
    """``hx://router/a/b?x=1`` to (["a", "b"], {"x": "1"}); the session part stays raw."""
    if not uri.startswith(ROOT):
        raise ResourceNotFoundError(f"unknown resource: {uri}")
    parts = urlsplit(uri)
    path: str = uri[len(ROOT) :].split("?", 1)[0]
    query: dict[str, str] = {key: values[0] for key, values in parse_qs(parts.query).items()}
    if path.startswith("sessions/") and path.endswith("/messages"):
        return ["sessions", unquote(path[len("sessions/") : -len("/messages")]), "messages"], query
    return [piece for piece in path.split("/") if piece], query


def recent_page(settings: Settings, user_id: int, session: str, limit: int) -> JsonDict:
    address = parse_session(session)
    require_owned(settings, user_id, address.instance_id)
    # 先取游标再读最近 N 条: 读期间新到的消息会出现在下一页, 至少一次, 不会丢
    cursor: str = latest_cursor(settings, address.instance_id)
    stored = recent_messages(settings, address.instance_id, address.address, limit)
    return {
        "session": session,
        "messages": [event_view(item.to_dict()) for item in stored],
        "next_cursor": cursor,
        "has_more": False,
    }


def payload_of(settings: Settings, user_id: int, scopes: frozenset[str], uri: str) -> JsonDict:
    pieces, query = split_uri(uri)
    if pieces == ["capabilities"]:
        return capabilities_list("")
    if pieces == ["sources"]:
        return sources_list(settings, user_id)
    if len(pieces) == 2 and pieces[0] == "instances" and pieces[1].isdigit():
        instance_id: int = int(pieces[1])
        require_owned(settings, user_id, instance_id)
        listed: object = sources_list(settings, user_id)["sources"]
        view: JsonDict = next(
            (
                dict(item)
                for item in (listed if isinstance(listed, list) else [])
                if isinstance(item, dict) and item.get("instance_id") == instance_id
            ),
            {"instance_id": instance_id},
        )
        return {**view, "cursor": latest_cursor(settings, instance_id)}
    if len(pieces) == 3 and pieces[0] == "sessions" and pieces[1]:
        raw: str = query.get("limit", "")
        limit: int = max(1, min(int(raw) if raw.isdigit() else DEFAULT_RECENT, MAX_RECENT))
        if query.get("cursor"):
            return pull(
                settings, user_id, pieces[1], query["cursor"], limit=limit, direction="both"
            )
        return recent_page(settings, user_id, pieces[1], limit)
    if len(pieces) == 2 and pieces[0] == "subscriptions" and pieces[1].isdigit():
        require_scope(scopes, SUBSCRIPTIONS)
        return get_route(settings, user_id, int(pieces[1])).to_dict()
    if len(pieces) == 2 and pieces[0] == "deliveries":
        delivery: JsonDict | None = delivery_status(settings, user_id, delivery_id=pieces[1])
        if delivery is not None:
            return delivery
    raise ResourceNotFoundError(f"unknown resource: {uri}")


# 资源挂在已有领域对象上, 读时现查不缓存; 不属于调用方的对象一律当作不存在
def read_resource(settings: Settings, user_id: int, scopes: frozenset[str], uri: str) -> JsonDict:
    """``resources/read`` result: one JSON text content."""
    try:
        payload: JsonDict = payload_of(settings, user_id, scopes, uri)
    except (SessionNotFoundError, RouteNotFoundError) as error:
        raise ResourceNotFoundError(str(error)) from error
    text: str = json.dumps(payload, ensure_ascii=False)
    return {"contents": [{"uri": uri, "mimeType": JSON_TYPE, "text": text}]}
