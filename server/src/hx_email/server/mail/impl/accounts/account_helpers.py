"""Shared helpers for email account operations (no circular deps on email_accounts)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from sqlite3 import Connection, Row
from typing import TYPE_CHECKING

from hx_email.config import Settings
from hx_email.database import utc_now_iso
from hx_email.server.auth import require_inserted_id
from hx_email.server.mail.usable_emails import UsableEmail

if TYPE_CHECKING:
    from hx_email.server.mail.email_accounts import EmailAccount


@dataclass(frozen=True)
class AccountPage:
    accounts: tuple[EmailAccount, ...]
    total_count: int
    page: int
    page_size: int


class DuplicateUsableEmailError(ValueError):
    pass


class InvalidAliasAddressError(ValueError):
    pass


class InvalidPrimaryAddressError(ValueError):
    pass


def normalize_primary_address(address: str) -> str:
    normalized: str = address.strip().lower()
    local_part, separator, domain = normalized.partition("@")
    if (
        not local_part
        or separator != "@"
        or not domain
        or "." not in domain
        or any(character.isspace() for character in normalized)
    ):
        raise InvalidPrimaryAddressError("Enter a valid email address")
    return normalized


def update_primary_usable_email(
    connection: Connection,
    user_id: int,
    account_id: int,
    address: str,
) -> str:
    normalized: str = normalize_primary_address(address)
    try:
        connection.execute(
            "UPDATE usable_emails SET address = ?"
            " WHERE user_id = ? AND email_account_id = ? AND kind = 'primary'",
            (normalized, user_id, account_id),
        )
    except sqlite3.IntegrityError as error:
        raise DuplicateUsableEmailError(
            "Usable email address already exists for this user"
        ) from error
    return normalized


def is_plus_subaddress(address: str) -> bool:
    local_part, separator, _domain = address.partition("@")
    return bool(separator) and "+" in local_part


def usable_email_from_row(row: Row) -> UsableEmail:
    return UsableEmail(
        id=row["id"],
        address=row["address"],
        label=row["label"],
        kind=row["kind"],
        status=row["status"],
        created_at=row["created_at"],
    )


def add_alias_email(
    connection: Connection,
    user_id: int,
    account_id: int,
    address: str,
    label: str,
) -> UsableEmail:
    if is_plus_subaddress(address):
        raise InvalidAliasAddressError("Alias address must be a real mailbox address")
    try:
        created_at: str = utc_now_iso()
        cursor = connection.execute(
            """
            INSERT INTO usable_emails (
                user_id, email_account_id, address, label, kind, status, active, created_at
            )
            VALUES (?, ?, ?, ?, 'alias', 'active', 1, ?)
            """,
            (user_id, account_id, address, label, created_at),
        )
    except sqlite3.IntegrityError as error:
        raise DuplicateUsableEmailError(
            "Usable email address already exists for this user"
        ) from error
    return UsableEmail(
        id=require_inserted_id(cursor.lastrowid),
        address=address,
        label=label,
        kind="alias",
        status="active",
        created_at=created_at,
    )


def _get_account(settings: Settings, user_id: int, account_id: int) -> EmailAccount | None:
    # 惰性导入避免与 email_accounts 循环依赖 (email_accounts -> account_helpers)
    from hx_email.server.mail.email_accounts import get_email_account

    return get_email_account(settings, user_id, account_id)


def _age_cutoff_iso(days: int) -> str:
    """ISO timestamp (UTC, Z suffix, ms precision) of `now - days`, matching utc_now_iso()."""
    from datetime import UTC, datetime, timedelta

    cutoff: datetime = datetime.now(UTC) - timedelta(days=days)
    return cutoff.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def search_email_accounts(
    settings: Settings,
    user_id: int,
    query: str,
) -> tuple[EmailAccount, ...]:
    """Full-text search across email addresses, remarks, and provider names."""
    from hx_email.database import connect

    with connect(settings) as connection:
        like = f"%{query}%"
        rows = connection.execute(
            """
            SELECT id
            FROM email_accounts
            WHERE user_id = ?
              AND (primary_address LIKE ?
                   OR remark LIKE ?
                   OR provider LIKE ?)
            ORDER BY id
            """,
            (user_id, like, like, like),
        ).fetchall()
    accounts = (_get_account(settings, user_id, row["id"]) for row in rows)
    return tuple(account for account in accounts if account is not None)


def _build_enhanced_query(
    user_id: int,
    group_id: int | None = None,
    search: str | None = None,
    tag_id: int | None = None,
    tag_ids: list[int] | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
    min_age_days: int | None = None,
    max_age_days: int | None = None,
) -> tuple[str, list[object]]:
    where = ["ea.user_id = ?"]
    params: list[object] = [user_id]
    joins: list[str] = []
    if group_id is not None:
        where.append("ea.group_id = ?")
        params.append(group_id)
    if search:
        like = f"%{search}%"
        where.append("(ea.primary_address LIKE ? OR ea.remark LIKE ? OR ea.provider LIKE ?)")
        params.extend([like, like, like])
    # 按初次导入时间 (email_accounts.created_at) 过滤存活天数:
    # min_age_days=N -> 已导入至少 N 天; max_age_days=M -> 导入不足 M 天
    if min_age_days is not None:
        where.append("ea.created_at != '' AND ea.created_at <= ?")
        params.append(_age_cutoff_iso(min_age_days))
    if max_age_days is not None:
        where.append("ea.created_at > ?")
        params.append(_age_cutoff_iso(max_age_days))
    if tag_id is not None:
        joins.append(
            """JOIN usable_emails ue_filter
               ON ue_filter.email_account_id = ea.id
              AND ue_filter.user_id = ea.user_id"""
        )
        joins.append("JOIN usable_email_tags ut_filter ON ut_filter.usable_email_id = ue_filter.id")
        where.append("ut_filter.tag_id = ?")
        params.append(tag_id)
    if tag_ids:
        tag_set = list(dict.fromkeys(tag_ids))
        placeholders = ",".join("?" for _ in tag_set)
        joins.append(
            """JOIN usable_emails ue_multi
               ON ue_multi.email_account_id = ea.id
              AND ue_multi.user_id = ea.user_id"""
        )
        joins.append(
            f"""JOIN usable_email_tags ut_multi
               ON ut_multi.usable_email_id = ue_multi.id
              AND ut_multi.tag_id IN ({placeholders})"""
        )
        params.extend(tag_set)
    where_sql, join_sql = " AND ".join(where), " ".join(joins)
    allowed_sort = {"id", "primary_address", "provider", "status", "created_at", "remark"}
    order = "DESC" if sort_order and sort_order.upper() == "DESC" else "ASC"
    sort_expr: str = "(SELECT MIN(created_at) FROM usable_emails WHERE email_account_id=ea.id)"
    if sort_by != "created_at":
        sort_expr = f"ea.{sort_by if sort_by in allowed_sort else 'id'}"
    return (
        f"""
        SELECT DISTINCT ea.id
        FROM email_accounts ea
        {join_sql}
        WHERE {where_sql}
        ORDER BY {sort_expr} {order}, ea.id {order}
        """,
        params,
    )


def list_email_accounts_enhanced(
    settings: Settings,
    user_id: int,
    *,
    group_id: int | None = None,
    page: int = 1,
    page_size: int = 50,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
    tag_id: int | None = None,
    tag_ids: list[int] | None = None,
    min_age_days: int | None = None,
    max_age_days: int | None = None,
) -> AccountPage:
    """Enhanced listing with pagination, filtering, and sorting."""
    from hx_email.database import connect

    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    query, params = _build_enhanced_query(
        user_id,
        group_id=group_id,
        search=search,
        tag_id=tag_id,
        tag_ids=tag_ids,
        sort_by=sort_by,
        sort_order=sort_order,
        min_age_days=min_age_days,
        max_age_days=max_age_days,
    )
    with connect(settings) as connection:
        total = connection.execute(
            f"SELECT COUNT(*) FROM ({query}) AS _cnt",
            params,
        ).fetchone()[0]
        offset = (page - 1) * page_size
        rows = connection.execute(
            f"{query} LIMIT ? OFFSET ?",
            (*params, page_size, offset),
        ).fetchall()
    accounts = (_get_account(settings, user_id, row["id"]) for row in rows)
    return AccountPage(
        accounts=tuple(account for account in accounts if account is not None),
        total_count=total,
        page=page,
        page_size=page_size,
    )
