"""``resources/subscribe`` and the notifications it produces.

A subscription is one persistent hub waiter (``server/hub/bus.py``) whose matcher is
built from the resource, so a stored message that touches it calls ``fire`` on the
publisher thread. ``fire`` only queues ``notifications/resources/updated`` on the MCP
session (coalesced per URI until the GET stream sends it); no database work happens
on the publisher thread, and with no GET stream ever opened nothing is queued.

``announce_list_changed`` pushes ``notifications/resources/list_changed`` to every
session of a user; subscription create/delete and instance create/delete call it.
"""

from __future__ import annotations

from typing import Final

from hx_email.api.impl.mcp.session_table import TABLE, McpSession
from hx_email.api.impl.mcp_resources.catalog import ResourceNotFoundError, split_uri
from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.access.scopes import SUBSCRIPTIONS, require_scope
from hx_email.server.gateway.providers import require_owned
from hx_email.server.hub.bus import BUS, Matcher, Waiter, matcher_for
from hx_email.server.hub.subscriptions import get_route
from hx_email.server.router.errors import RouteNotFoundError, SessionNotFoundError
from hx_email.server.router.impl.reader import owned_instances, parse_source

MAX_WATCHES: Final[int] = 32
NEVER: Final[Matcher] = Matcher(instances=frozenset())
JsonDict = dict[str, object]


class WatchError(ValueError):
    """The resource cannot be subscribed to, or the session holds too many watches."""


def owned_ids(settings: Settings, user_id: int) -> list[int]:
    with connect(settings) as connection:
        return owned_instances(connection, user_id)


def matcher_of(settings: Settings, user_id: int, scopes: frozenset[str], uri: str) -> Matcher:
    """Which hub hits change ``uri``; runs in a worker thread (SQLite)."""
    pieces, _query = split_uri(uri)
    try:
        if pieces in (["capabilities"], ["sources"]):
            return NEVER  # 静态资源: 允许订阅, 集合变化走 list_changed
        if len(pieces) == 2 and pieces[0] == "instances" and pieces[1].isdigit():
            require_owned(settings, user_id, int(pieces[1]))
            return Matcher(instances=frozenset({int(pieces[1])}))
        if len(pieces) == 3 and pieces[0] == "sessions" and pieces[1]:
            return matcher_for(parse_source(pieces[1]), owned_ids(settings, user_id))
        if len(pieces) == 2 and pieces[0] == "subscriptions" and pieces[1].isdigit():
            require_scope(scopes, SUBSCRIPTIONS)
            route = get_route(settings, user_id, int(pieces[1]))
            return matcher_for(route.scope, owned_ids(settings, user_id))
    except (SessionNotFoundError, RouteNotFoundError) as error:
        raise ResourceNotFoundError(str(error)) from error
    if len(pieces) == 2 and pieces[0] == "deliveries":
        raise WatchError("deliveries are not subscribable; poll delivery_status")
    raise ResourceNotFoundError(f"unknown resource: {uri}")


def updated(uri: str) -> JsonDict:
    return {
        "jsonrpc": "2.0",
        "method": "notifications/resources/updated",
        "params": {"uri": uri},
    }


# 订阅即一个常驻 hub 等待者, 回调只往会话队列放一条按 URI 合并的通知, 不碰数据库
# 决策记录: .agents/notes/implemented/feature/2026-11-09-mcp-completion.md
def subscribe(session: McpSession, uri: str, matcher: Matcher) -> None:
    with session.lock:
        if uri in session.watches:
            return
        if len(session.watches) >= MAX_WATCHES:
            raise WatchError(f"at most {MAX_WATCHES} resource subscriptions per session")

        def fire() -> None:
            session.emit(updated(uri), coalesce=uri)

        waiter = Waiter(matcher, fire)
        session.watches[uri] = waiter
    BUS.register(waiter)
    if session.ended:  # 与 DELETE 赛跑: 会话已结束就撤掉刚注册的等待者
        BUS.unregister(waiter)


def unsubscribe(session: McpSession, uri: str) -> bool:
    with session.lock:
        waiter: Waiter | None = session.watches.pop(uri, None)
    if waiter is None:
        return False
    BUS.unregister(waiter)
    return True


def announce_list_changed(user_id: int) -> int:
    """Tell every session of ``user_id`` that its resource set changed."""
    message: JsonDict = {"jsonrpc": "2.0", "method": "notifications/resources/list_changed"}
    return sum(1 for s in TABLE.of_user(user_id) if s.emit(message, coalesce="list_changed"))
