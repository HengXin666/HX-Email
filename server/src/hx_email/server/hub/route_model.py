"""The subscription row as a value: filter, delivery target, ack and push positions.

Split out of ``subscriptions.py`` in the push stage so the CRUD module stays under the
300 line ceiling once webhook targets joined the row. ``ack_position`` is what the
consumer confirmed; ``push_position`` is how far the webhook feeder has queued batches.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from typing import Final

from hx_email.config import Settings
from hx_email.server.contract.address import address_of_legacy, is_v2
from hx_email.server.push.webhook_target import WebhookTarget, open_target
from hx_email.server.router.cursor import encode_cursor
from hx_email.server.router.errors import RouteInvalidError
from hx_email.server.router.impl.reader import Source, parse_source

BACKLOG_CAP: Final[int] = 999
DIRECTIONS: Final[frozenset[str]] = frozenset({"inbound", "outbound", "both"})
DELIVERIES: Final[frozenset[str]] = frozenset({"pull", "webhook"})
FILTER_KEYS: Final[frozenset[str]] = frozenset(
    {"direction", "kinds", "exclude_self", "mention_self", "contains"}
)
STATUSES: Final[frozenset[str]] = frozenset({"active", "paused"})
ROUTE_COLUMNS: Final[str] = (
    "id, user_id, name, source_prefix, filter_json, delivery, target_encrypted, status, "
    "ack_cursor, push_cursor, created_at, updated_at, expires_at"
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

    def dumps(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


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
    push_position: int = 0
    target: WebhookTarget | None = None

    def cursor(self, position: int | None = None) -> str:
        """A position (the ack by default) as a cursor valid for this route's scope."""
        return encode_cursor(
            self.scope.instance_id or 0, self.ack_position if position is None else position
        )

    def to_dict(self, backlog: int | None = None) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "address": self.source if is_v2(self.source) else address_of_legacy(self.source),
            "filter": {**asdict(self.filter), "kinds": list(self.filter.kinds)},
            "delivery": self.delivery,
            "webhook": (
                {"url": self.target.url, "push_cursor": self.cursor(self.push_position)}
                if self.delivery == "webhook" and self.target is not None
                else None
            ),
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


def row_to_route(settings: Settings, row: sqlite3.Row) -> Route:
    source: str = str(row["source_prefix"])
    sealed: str = str(row["target_encrypted"] or "")
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
        push_position=int(row["push_cursor"] or 0),
        target=open_target(settings, sealed) if sealed else None,
    )
