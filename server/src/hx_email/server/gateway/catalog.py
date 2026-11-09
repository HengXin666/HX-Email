"""Discovery side of the gateway: sources, sessions, session selection (spec 5.1 to 5.3).

Session lists merge two places: what the platform reports right now (QQ friends and
groups) and what the store has already seen (every GitHub thread, QQ temp sessions,
chats whose friend list call failed). The store half means a session stays listable
while the account is offline, and GitHub, which has no "list my threads" call worth
its rate cost, is listable at all.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Final

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.contract.address import address_of_legacy
from hx_email.server.contract.builtin import REGISTRY
from hx_email.server.contract.event import CONTRACT_VERSION
from hx_email.server.gateway.impl.breaker import BREAKER
from hx_email.server.gateway.providers import (
    HUB,
    InstanceRow,
    owned_instances,
    profile_for,
    require_owned,
)
from hx_email.server.router.cursor import earliest_cursor
from hx_email.server.router.envelope import SessionAddress, parse_session
from hx_email.server.router.errors import SessionNotFoundError
from hx_email.server.router.impl.reader import latest_cursor
from hx_email.server.router.impl.shaper import RateProfile
from hx_email.server.router.provider import SessionRef

LOGGER: logging.Logger = logging.getLogger("hx_email.gateway.catalog")
SENDABLE_TYPES: Final[frozenset[str]] = frozenset(
    {"private", "group", "temp", "qzonepost", "issue", "repo", "channel"}
)
MAX_SESSIONS: Final[int] = 200
OFFICIAL_KINDS: Final[frozenset[str]] = frozenset({"github", "github_user"})


def source_state(instance: InstanceRow) -> str:
    if instance.kind == "github":
        return "online" if instance.config.get("app_id") else "stopped"
    return instance.status if instance.status in ("online", "connecting", "error") else "stopped"


def capabilities_list(platform: str = "") -> dict[str, object]:
    """Platform declarations (address kinds, event kinds, signals, actions); no auth data."""
    return {"contract": CONTRACT_VERSION, "platforms": REGISTRY.listing(platform)}


# 会话列表 = 平台实时列表 + 库里见过的会话; 平台离线时会话仍可列出, GitHub 线程只能从库里来
def sources_list(settings: Settings, user_id: int, platform: str = "") -> dict[str, object]:
    items: list[dict[str, object]] = []
    for instance in owned_instances(settings, user_id):
        if platform and instance.kind != platform:
            continue
        outbound, held_until = BREAKER.outbound(instance.id)
        items.append(
            {
                "platform": instance.kind,
                "instance_id": instance.id,
                "address": f"{instance.kind}:{instance.id}",
                "name": instance.name,
                "state": source_state(instance),
                "account_id": instance.config.get(
                    "login" if instance.kind == "github_user" else "app_slug", ""
                ),
                "outbound": outbound,
                "held_until": held_until,
                "risk_level": "official" if instance.kind in OFFICIAL_KINDS else "third_party",
            }
        )
    return {"sources": items}


def stored_sessions(settings: Settings, instance: InstanceRow) -> list[SessionRef]:
    with connect(settings) as connection:
        rows: list[sqlite3.Row] = connection.execute(
            "SELECT chat_id, chat_type, MAX(sender_name) AS title FROM messaging_messages "
            "WHERE instance_id = ? GROUP BY chat_id ORDER BY MAX(id) DESC LIMIT ?",
            (instance.id, MAX_SESSIONS),
        ).fetchall()
    refs: list[SessionRef] = []
    for row in rows:
        chat_id: str = str(row["chat_id"])
        if ":" not in chat_id:
            chat_id = f"{instance.kind}:{instance.id}:{row['chat_type'] or 'private'}:{chat_id}"
        try:
            address: SessionAddress = parse_session(chat_id)
        except SessionNotFoundError:
            continue
        title: str = address.peer if address.session_type != "private" else str(row["title"] or "")
        refs.append(
            SessionRef(
                address.address,
                address.platform,
                instance.id,
                address.session_type,
                address.peer,
                title or address.peer,
            )
        )
    return refs


def live_sessions(settings: Settings, instance: InstanceRow) -> list[SessionRef]:
    try:
        return HUB.provider_for(settings, instance).list_sessions(instance.id)
    except Exception as error:  # an offline account still lists stored sessions
        LOGGER.info("live session list failed for instance %s: %s", instance.id, error)
        return []


def collect_sessions(settings: Settings, instance: InstanceRow) -> list[SessionRef]:
    merged: dict[str, SessionRef] = {}
    for ref in [*live_sessions(settings, instance), *stored_sessions(settings, instance)]:
        merged.setdefault(ref.address, ref)
    return list(merged.values())


def sessions_list(
    settings: Settings,
    user_id: int,
    instance_id: int,
    *,
    session_type: str = "",
    query: str = "",
    limit: int = 50,
) -> dict[str, object]:
    instance: InstanceRow = require_owned(settings, user_id, instance_id)
    needle: str = query.strip().lower()
    out: list[dict[str, object]] = []
    for ref in collect_sessions(settings, instance):
        if session_type and ref.session_type != session_type:
            continue
        if needle and needle not in ref.title.lower() and needle not in ref.session_id.lower():
            continue
        out.append(
            {
                "session": ref.address,
                "address": address_of_legacy(ref.address),
                "session_type": ref.session_type,
                "title": ref.title,
            }
        )
        if len(out) >= max(1, min(limit, MAX_SESSIONS)):
            break
    return {"sessions": out}


def session_select(
    settings: Settings, user_id: int, session: str, start: str = "now"
) -> dict[str, object]:
    address: SessionAddress = parse_session(session)
    instance: InstanceRow = require_owned(settings, user_id, address.instance_id)
    if instance.kind != address.platform:
        raise SessionNotFoundError(f"{session} does not match instance platform {instance.kind}")
    profile: RateProfile = profile_for(instance, address.session_type)
    cursor: str = (
        earliest_cursor(instance.id).encode()
        if start == "earliest"
        else latest_cursor(settings, instance.id)
    )
    outbound, _until = BREAKER.outbound(instance.id)
    return {
        "session": address.address,
        "address": address_of_legacy(address.address),
        "title": address.peer,
        "can_send": address.session_type in SENDABLE_TYPES and outbound == "open",
        "cursor": cursor,
        "limits": {
            "per_session_interval_seconds": profile.per_session_interval_seconds,
            "per_account_per_minute": profile.per_account_per_minute,
            "max_text_length": profile.max_text_length,
        },
    }
