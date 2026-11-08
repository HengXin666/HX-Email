"""Persistent subscriptions: rows of ``router_routes`` that remember where a consumer is.

A subscription is a source (v1 prefix or v2 address/selector), a filter applied to the
contract v2 event view, and an ``ack_cursor`` position that only moves forward. It
survives restarts and reconnects: a consumer that comes back reads from its ack and
misses nothing. ``delivery`` is ``pull`` this round (long-poll or SSE on the route);
webhook and WebSocket delivery reuse the same row in the push stage.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from typing import Final

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.contract.address import address_of_legacy, is_v2
from hx_email.server.router.cursor import decode_cursor, encode_cursor
from hx_email.server.router.errors import (
    CursorInvalidError,
    RouteInvalidError,
    RouteLimitError,
    RouteNotFoundError,
    SessionNotFoundError,
)
from hx_email.server.router.impl.reader import (
    Source,
    build_query,
    owned_instances,
    parse_source,
)

MAX_ROUTES_PER_USER: Final[int] = 50
BACKLOG_CAP: Final[int] = 999
DIRECTIONS: Final[frozenset[str]] = frozenset({"inbound", "outbound", "both"})
DELIVERIES: Final[frozenset[str]] = frozenset({"pull"})
FILTER_KEYS: Final[frozenset[str]] = frozenset(
    {"direction", "kinds", "exclude_self", "mention_self", "contains"}
)
STATUSES: Final[frozenset[str]] = frozenset({"active", "paused"})
ROUTE_COLUMNS: Final[str] = (
    "id, user_id, name, source_prefix, filter_json, delivery, status, ack_cursor, "
    "created_at, updated_at, expires_at"
)


@dataclass(frozen=True)
class RouteFilter:
    """What a consumer wants out of its source; tested on the v2 event view."""

    direction: str = "inbound"
    kinds: tuple[str, ...] = ()
    exclude_self: bool = True
    mention_self: bool = False
    contains: str = ""

    def accepts(self, view: dict[str, object]) -> bool:
        flags: object = view.get("flags")
        flag_map: dict[str, object] = flags if isinstance(flags, dict) else {}
        if self.kinds and str(view.get("kind") or "") not in self.kinds:
            return False
        if self.exclude_self and flag_map.get("from_self") is True:
            return False
        if self.mention_self and flag_map.get("mention_self") is not True:
            return False
        return not self.contains or self.contains.lower() in str(view.get("text") or "").lower()


def filter_from(payload: object) -> RouteFilter:
    """Validate a filter dict from REST/MCP or the database; unknown keys are refused."""
    data: dict[str, object] = payload if isinstance(payload, dict) else {}
    unknown: set[str] = set(data) - FILTER_KEYS
    if unknown:
        raise RouteInvalidError(f"unknown filter keys: {sorted(unknown)}")
    direction: str = str(data.get("direction") or "inbound")
    if direction not in DIRECTIONS:
        raise RouteInvalidError(f"direction must be one of {sorted(DIRECTIONS)}")
    kinds_value: object = data.get("kinds") or []
    if not isinstance(kinds_value, list) or not all(isinstance(k, str) for k in kinds_value):
        raise RouteInvalidError("kinds must be a list of strings")
    return RouteFilter(
        direction=direction,
        kinds=tuple(kinds_value),
        exclude_self=bool(data.get("exclude_self", True)),
        mention_self=bool(data.get("mention_self", False)),
        contains=str(data.get("contains") or "")[:200],
    )


@dataclass(frozen=True)
class Route:
    id: int
    user_id: int
    name: str
    source: str
    filter: RouteFilter
    delivery: str
    status: str
    ack_position: int
    created_at: str
    updated_at: str
    expires_at: str | None = None
    scope: Source = field(default_factory=lambda: Source(platform=""))

    def cursor(self) -> str:
        """The ack position as a cursor valid for this route's scope."""
        return encode_cursor(self.scope.instance_id or 0, self.ack_position)

    def to_dict(self, backlog: int | None = None) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "address": self.source if is_v2(self.source) else address_of_legacy(self.source),
            "filter": {**asdict(self.filter), "kinds": list(self.filter.kinds)},
            "delivery": self.delivery,
            "status": self.status,
            "ack_cursor": self.cursor(),
            "created_at": self.created_at,
            "updated_at": self.updated_at or self.created_at,
            "expires_at": self.expires_at,
        }
        if backlog is not None:
            data["backlog"] = backlog
            data["backlog_capped"] = backlog >= BACKLOG_CAP
        return data


def row_to_route(row: sqlite3.Row) -> Route:
    source: str = str(row["source_prefix"])
    return Route(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        name=str(row["name"] or ""),
        source=source,
        filter=filter_from(json.loads(str(row["filter_json"] or "{}"))),
        delivery=str(row["delivery"]),
        status=str(row["status"]),
        ack_position=int(row["ack_cursor"] or 0),
        created_at=str(row["created_at"] or ""),
        updated_at=str(row["updated_at"] or ""),
        expires_at=str(row["expires_at"]) if row["expires_at"] else None,
        scope=parse_source(source),
    )


def newest_position(connection: sqlite3.Connection, scope: Source, owned: list[int]) -> int:
    ids: list[int] = [scope.instance_id] if scope.instance_id is not None else owned
    if not ids:
        return 0
    marks: str = ", ".join("?" for _ in ids)
    row: sqlite3.Row | None = connection.execute(
        f"SELECT MAX(id) AS newest FROM messaging_messages WHERE instance_id IN ({marks})", ids
    ).fetchone()
    return int(row["newest"]) if row is not None and row["newest"] else 0


def backlog_of(connection: sqlite3.Connection, route: Route, owned: list[int]) -> int:
    """Unfiltered rows after the ack in scope, capped so a huge backlog stays cheap."""
    sql, params = build_query(
        route.scope, owned, route.ack_position, route.filter.direction, BACKLOG_CAP - 1
    )
    row: sqlite3.Row | None = connection.execute(
        f"SELECT COUNT(*) AS pending FROM ({sql})", params
    ).fetchone()
    return int(row["pending"]) if row is not None else 0


def create_route(
    settings: Settings,
    user_id: int,
    *,
    source: str,
    name: str = "",
    filter_data: object = None,
    start: str = "now",
) -> dict[str, object]:
    """Register a subscription; ``start`` is ``now`` (only new messages) or ``earliest``."""
    scope: Source = parse_source(source)
    route_filter: RouteFilter = filter_from(filter_data)
    if start not in ("now", "earliest"):
        raise RouteInvalidError("start must be now or earliest")
    with connect(settings) as connection:
        owned: list[int] = owned_instances(connection, user_id)
        if scope.instance_id is not None and scope.instance_id not in owned:
            raise SessionNotFoundError(f"instance {scope.instance_id} is not yours")
        count_row: sqlite3.Row | None = connection.execute(
            "SELECT COUNT(*) AS n FROM router_routes WHERE user_id = ?", (user_id,)
        ).fetchone()
        if count_row is not None and int(count_row["n"]) >= MAX_ROUTES_PER_USER:
            raise RouteLimitError(f"at most {MAX_ROUTES_PER_USER} subscriptions per account")
        position: int = newest_position(connection, scope, owned) if start == "now" else 0
        cursor: sqlite3.Cursor = connection.execute(
            "INSERT INTO router_routes (user_id, name, source_prefix, filter_json, delivery, "
            "status, ack_cursor, updated_at) VALUES (?, ?, ?, ?, 'pull', 'active', ?, "
            "datetime('now'))",
            (
                user_id,
                name.strip()[:64],
                source,
                json.dumps(asdict(route_filter), ensure_ascii=False),
                position,
            ),
        )
        connection.commit()
        route_id: int = int(cursor.lastrowid or 0)
    return get_route(settings, user_id, route_id).to_dict(backlog=0)


def get_route(settings: Settings, user_id: int, route_id: int) -> Route:
    with connect(settings) as connection:
        row: sqlite3.Row | None = connection.execute(
            f"SELECT {ROUTE_COLUMNS} FROM router_routes WHERE id = ? AND user_id = ?",
            (route_id, user_id),
        ).fetchone()
    if row is None:
        raise RouteNotFoundError(f"subscription {route_id} not found")
    return row_to_route(row)


def list_routes(settings: Settings, user_id: int) -> dict[str, object]:
    with connect(settings) as connection:
        owned: list[int] = owned_instances(connection, user_id)
        rows: list[sqlite3.Row] = connection.execute(
            f"SELECT {ROUTE_COLUMNS} FROM router_routes WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
        routes: list[Route] = [row_to_route(row) for row in rows]
        items: list[dict[str, object]] = [
            route.to_dict(backlog=backlog_of(connection, route, owned)) for route in routes
        ]
    return {"subscriptions": items, "limit": MAX_ROUTES_PER_USER}


def update_route(
    settings: Settings,
    user_id: int,
    route_id: int,
    *,
    name: str | None = None,
    status: str | None = None,
    filter_data: object = None,
) -> dict[str, object]:
    route: Route = get_route(settings, user_id, route_id)
    if status is not None and status not in STATUSES:
        raise RouteInvalidError(f"status must be one of {sorted(STATUSES)}")
    new_filter: RouteFilter = route.filter if filter_data is None else filter_from(filter_data)
    with connect(settings) as connection:
        connection.execute(
            "UPDATE router_routes SET name = ?, status = ?, filter_json = ?, "
            "updated_at = datetime('now') WHERE id = ? AND user_id = ?",
            (
                route.name if name is None else name.strip()[:64],
                route.status if status is None else status,
                json.dumps(asdict(new_filter), ensure_ascii=False),
                route_id,
                user_id,
            ),
        )
        connection.commit()
    return get_route(settings, user_id, route_id).to_dict()


def delete_route(settings: Settings, user_id: int, route_id: int) -> dict[str, object]:
    get_route(settings, user_id, route_id)
    with connect(settings) as connection:
        connection.execute(
            "DELETE FROM router_routes WHERE id = ? AND user_id = ?", (route_id, user_id)
        )
        connection.commit()
    return {"id": route_id, "deleted": True}


def ack_route(settings: Settings, user_id: int, route_id: int, cursor: str) -> dict[str, object]:
    """Move the ack forward to ``cursor``; an older cursor is a no-op, never a rewind."""
    route: Route = get_route(settings, user_id, route_id)
    parsed = decode_cursor(cursor)
    if parsed.instance_id != (route.scope.instance_id or 0) and parsed.instance_id != 0:
        raise CursorInvalidError("cursor does not belong to this subscription's scope")
    with connect(settings) as connection:
        connection.execute(
            "UPDATE router_routes SET ack_cursor = MAX(ack_cursor, ?), "
            "updated_at = datetime('now') WHERE id = ? AND user_id = ?",
            (parsed.position, route_id, user_id),
        )
        connection.commit()
    return get_route(settings, user_id, route_id).to_dict()
