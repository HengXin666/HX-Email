"""Persistent subscriptions: rows of ``router_routes`` that remember where a consumer is.

A subscription is a source (v1 prefix or v2 address/selector), a filter applied to the
contract v2 event view, and an ``ack_cursor`` position that only moves forward. It
survives restarts and reconnects: a consumer that comes back reads from its ack and
misses nothing. ``delivery`` is ``pull`` (long-poll, SSE or WebSocket on the route) or
``webhook`` (the push feeder queues batches to the URL; a 2xx moves the ack).
"""

from __future__ import annotations

import sqlite3
from typing import Final

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.hub.route_model import (
    BACKLOG_CAP,
    DELIVERIES,
    ROUTE_COLUMNS,
    STATUSES,
    Route,
    RouteFilter,
    filter_from,
    row_to_route,
)
from hx_email.server.push.webhook_target import WebhookTarget, check_url, new_secret, seal_target
from hx_email.server.router.cursor import decode_cursor
from hx_email.server.router.errors import (
    CursorInvalidError,
    RouteInvalidError,
    RouteLimitError,
    RouteNotFoundError,
    SessionNotFoundError,
)
from hx_email.server.router.impl.reader import Source, build_query, owned_instances, parse_source

MAX_ROUTES_PER_USER: Final[int] = 50


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


def target_for(
    delivery: str, webhook_url: str | None, current: WebhookTarget | None
) -> tuple[WebhookTarget | None, bool]:
    """Resolve the webhook target for a delivery mode; True when a secret was minted."""
    if delivery not in DELIVERIES:
        raise RouteInvalidError(f"delivery must be one of {sorted(DELIVERIES)}")
    if delivery == "pull":
        return current, False
    url: str = webhook_url if webhook_url is not None else (current.url if current else "")
    if not url:
        raise RouteInvalidError("webhook delivery needs webhook_url")
    if current is not None and current.secret:
        return WebhookTarget(check_url(url), current.secret), False
    return WebhookTarget(check_url(url), new_secret()), True


def with_secret(route: Route, minted: bool, data: dict[str, object]) -> dict[str, object]:
    """The secret goes out exactly once: in the reply that created or rotated it."""
    if minted and route.target is not None:
        data["webhook_secret"] = route.target.secret
    return data


# 推送阶段: webhook 目标 (URL 与密钥) 加密存在同一行 target_encrypted, 密钥只在创建或轮换时返回一次
# 决策记录: .agents/notes/implemented/feature/2026-11-08-router-push-transports.md
def create_route(
    settings: Settings,
    user_id: int,
    *,
    source: str,
    name: str = "",
    filter_data: object = None,
    start: str = "now",
    delivery: str = "pull",
    webhook_url: str | None = None,
) -> dict[str, object]:
    """Register a subscription; ``start`` is ``now`` (only new messages) or ``earliest``."""
    scope: Source = parse_source(source)
    route_filter: RouteFilter = filter_from(filter_data)
    if start not in ("now", "earliest"):
        raise RouteInvalidError("start must be now or earliest")
    target, minted = target_for(delivery, webhook_url, None)
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
            "target_encrypted, status, ack_cursor, push_cursor, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, datetime('now'))",
            (
                user_id,
                name.strip()[:64],
                source,
                route_filter.dumps(),
                delivery,
                seal_target(settings, target) if target else "",
                position,
                position,
            ),
        )
        connection.commit()
        route_id: int = int(cursor.lastrowid or 0)
    route: Route = get_route(settings, user_id, route_id)
    return with_secret(route, minted, route.to_dict(backlog=0))


def get_route(settings: Settings, user_id: int, route_id: int) -> Route:
    with connect(settings) as connection:
        row: sqlite3.Row | None = connection.execute(
            f"SELECT {ROUTE_COLUMNS} FROM router_routes WHERE id = ? AND user_id = ?",
            (route_id, user_id),
        ).fetchone()
    if row is None:
        raise RouteNotFoundError(f"subscription {route_id} not found")
    return row_to_route(settings, row)


def load_route(settings: Settings, route_id: int) -> Route | None:
    """Owner-agnostic load for the push workers, which act on behalf of the row's user."""
    with connect(settings) as connection:
        row: sqlite3.Row | None = connection.execute(
            f"SELECT {ROUTE_COLUMNS} FROM router_routes WHERE id = ?", (route_id,)
        ).fetchone()
    return row_to_route(settings, row) if row is not None else None


def webhook_routes(settings: Settings) -> list[Route]:
    """Every active webhook subscription, for the feeder to watch."""
    with connect(settings) as connection:
        rows: list[sqlite3.Row] = connection.execute(
            f"SELECT {ROUTE_COLUMNS} FROM router_routes "
            "WHERE delivery = 'webhook' AND status = 'active' ORDER BY id"
        ).fetchall()
    return [row_to_route(settings, row) for row in rows]


def list_routes(settings: Settings, user_id: int) -> dict[str, object]:
    with connect(settings) as connection:
        owned: list[int] = owned_instances(connection, user_id)
        rows: list[sqlite3.Row] = connection.execute(
            f"SELECT {ROUTE_COLUMNS} FROM router_routes WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
        routes: list[Route] = [row_to_route(settings, row) for row in rows]
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
    delivery: str | None = None,
    webhook_url: str | None = None,
    rotate_secret: bool = False,
) -> dict[str, object]:
    """Change a subscription; switching to webhook or rotating mints a new secret."""
    route: Route = get_route(settings, user_id, route_id)
    if status is not None and status not in STATUSES:
        raise RouteInvalidError(f"status must be one of {sorted(STATUSES)}")
    new_filter: RouteFilter = route.filter if filter_data is None else filter_from(filter_data)
    mode: str = route.delivery if delivery is None else delivery
    current: WebhookTarget | None = route.target
    if rotate_secret and current is not None:
        current = WebhookTarget(current.url, "")
    target, minted = target_for(mode, webhook_url, current)
    with connect(settings) as connection:
        connection.execute(
            "UPDATE router_routes SET name = ?, status = ?, filter_json = ?, delivery = ?, "
            "target_encrypted = ?, push_cursor = CASE WHEN delivery = ? THEN push_cursor "
            "ELSE ack_cursor END, updated_at = datetime('now') WHERE id = ? AND user_id = ?",
            (
                route.name if name is None else name.strip()[:64],
                route.status if status is None else status,
                new_filter.dumps(),
                mode,
                seal_target(settings, target) if target else "",
                mode,
                route_id,
                user_id,
            ),
        )
        if status == "active":
            # 暂停期间到点的 webhook 批次被置为 held; 恢复后按原顺序重新排队
            connection.execute(
                "UPDATE router_outbox SET status = 'queued', next_attempt_at = datetime('now') "
                "WHERE kind = 'webhook' AND route_id = ? AND status = 'held'",
                (route_id,),
            )
        connection.commit()
    updated: Route = get_route(settings, user_id, route_id)
    return with_secret(updated, minted, updated.to_dict())


def delete_route(settings: Settings, user_id: int, route_id: int) -> dict[str, object]:
    get_route(settings, user_id, route_id)
    with connect(settings) as connection:
        connection.execute(
            "DELETE FROM router_outbox WHERE kind = 'webhook' AND route_id = ?", (route_id,)
        )
        connection.execute(
            "DELETE FROM router_routes WHERE id = ? AND user_id = ?", (route_id, user_id)
        )
        connection.commit()
    return {"id": route_id, "deleted": True}


def advance(settings: Settings, route_id: int, column: str, position: int) -> None:
    """Move ``ack_cursor`` or ``push_cursor`` forward; never backwards."""
    if column not in ("ack_cursor", "push_cursor"):
        raise ValueError(column)
    with connect(settings) as connection:
        connection.execute(
            f"UPDATE router_routes SET {column} = MAX({column}, ?), "
            "updated_at = datetime('now') WHERE id = ?",
            (position, route_id),
        )
        connection.commit()


def ack_route(settings: Settings, user_id: int, route_id: int, cursor: str) -> dict[str, object]:
    """Move the ack forward to ``cursor``; an older cursor is a no-op, never a rewind."""
    route: Route = get_route(settings, user_id, route_id)
    parsed = decode_cursor(cursor)
    if parsed.instance_id != (route.scope.instance_id or 0) and parsed.instance_id != 0:
        raise CursorInvalidError("cursor does not belong to this subscription's scope")
    advance(settings, route_id, "ack_cursor", parsed.position)
    return get_route(settings, user_id, route_id).to_dict()
