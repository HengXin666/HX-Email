"""Read scopes: ``source`` strings to a narrowed SQL page query (spec section 7).

``parse_source`` turns ``source`` into a scope that narrows the SQL: v1 ``qq:``,
``qq:3:``, ``qq:3:group:``, a full v1 address, or any v2 address or selector.
Every read is ``WHERE id > ? ORDER BY id LIMIT n``; no OFFSET, no full scan.
"""

from __future__ import annotations

from dataclasses import dataclass

from hx_email.server.contract.address import AddressError, LegacyScope, is_v2, parse_address
from hx_email.server.contract.address import legacy_scope as v2_scope
from hx_email.server.contract.builtin import REGISTRY
from hx_email.server.router.envelope import parse_session
from hx_email.server.router.errors import SessionNotFoundError

PLATFORMS = REGISTRY.platform_names()
COLUMNS = (
    "id, instance_id, direction, chat_id, chat_type, sender_id, sender_name, text, "
    "reply_to, message_id, attachments_json, occurred_at, raw_json, raw_ref, is_self, "
    "created_at, dedup_key"
)


@dataclass(frozen=True)
class Source:
    """A narrowed read scope; None means "do not filter on this field"."""

    platform: str
    instance_id: int | None = None
    session_type: str | None = None
    chat_id: str | None = None
    patterns: tuple[str, ...] = ()


# v2 选择器翻译成 v1 精确值加 LIKE 模式, 仓库级前缀靠 patterns
# 决策记录: .agents/notes/implemented/feature/2026-11-08-router-contract-v2.md
def parse_source(source: str) -> Source:
    """Accept ``qq:``, ``qq:3:``, ``qq:3:group:``, a full v1 address, or v2."""
    if is_v2(source):
        try:
            scope: LegacyScope = v2_scope(parse_address(source))
        except AddressError as error:
            raise SessionNotFoundError(str(error)) from error
        return Source(scope.platform, scope.instance_id, None, scope.exact or None, scope.patterns)
    parts: list[str] = source.split(":")
    platform: str = parts[0]
    if platform not in PLATFORMS:
        raise SessionNotFoundError(f"unknown platform in source: {source!r}")
    if len(parts) == 2 and parts[1] == "":
        return Source(platform)
    if len(parts) < 3 or not parts[1].isdigit():
        raise SessionNotFoundError(f"cannot parse source: {source!r}")
    instance_id: int = int(parts[1])
    if instance_id <= 0:
        raise SessionNotFoundError(f"instance id must be positive: {source!r}")
    rest: list[str] = parts[2:]
    if rest == [""]:
        return Source(platform, instance_id)
    if len(rest) == 2 and rest[1] == "":
        return Source(platform, instance_id, session_type=rest[0])
    try:
        address = parse_session(source)
    except SessionNotFoundError as error:
        raise SessionNotFoundError(str(error)) from error
    return Source(platform, instance_id, session_type=address.session_type, chat_id=source)


def peer_of(address: str) -> str:
    """Peer id from a full address; a bare id comes back unchanged."""
    parts: list[str] = address.split(":")
    return parts[3] if len(parts) >= 4 else address


def build_query(
    scope: Source, instance_ids: list[int], start: int, direction: str, limit: int
) -> tuple[str, list[object]]:
    """Build the parameterised page query; a single-session read hits the index."""
    clauses: list[str] = []
    params: list[object] = []
    if scope.instance_id is not None:
        clauses.append("instance_id = ?")
        params.append(scope.instance_id)
    elif instance_ids:
        placeholders: str = ", ".join("?" for _ in instance_ids)
        clauses.append(f"instance_id IN ({placeholders})")
        params.extend(instance_ids)
    else:
        clauses.append("1 = 0")
    if scope.patterns:
        likes: list[str] = ["chat_id LIKE ? ESCAPE '\\'" for _ in scope.patterns]
        clauses.append("(" + " OR ".join(["chat_id = ?", *likes]) + ")")
        params.extend([scope.chat_id or "", *scope.patterns])
    elif scope.chat_id:
        # 两条写入路径的 chat_id 格式不同: 事件端点 (messaging/store.save_message) 存纯号,
        # 路由层 (router/impl/store.store_inbound) 存完整地址. 两种都认, 否则同一个会话
        # 会因为写入方不同而查不到.
        clauses.append("(chat_id = ? OR chat_id = ?)")
        params.append(scope.chat_id)
        params.append(peer_of(scope.chat_id))
    elif scope.session_type:
        clauses.append("chat_id LIKE ?")
        params.append(f"{scope.platform}:%:{scope.session_type}:%")
    if direction != "both":
        clauses.append("direction = ?")
        params.append(direction)
    clauses.append("id > ?")
    params.append(start)
    sql: str = (
        f"SELECT {COLUMNS} FROM messaging_messages WHERE "
        + " AND ".join(clauses)
        + " ORDER BY id ASC LIMIT ?"
    )
    params.append(limit + 1)
    return sql, params
