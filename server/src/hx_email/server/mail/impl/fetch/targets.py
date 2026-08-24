from __future__ import annotations

from dataclasses import dataclass

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail.verification.addresses import normalize_delivery_address


@dataclass(frozen=True)
class FetchAccountInfo:
    email_account_id: int | None
    last_refresh_at: str | None


@dataclass(frozen=True)
class FetchUsableEmail:
    id: int
    address: str
    kind: str = "custom"
    provider: str = ""


def resolve_fetch_account_info(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
) -> FetchAccountInfo:
    with connect(settings) as conn:
        row = conn.execute(
            """
            SELECT ue.address, ue.email_account_id, ea.last_refresh_at
            FROM usable_emails ue
            LEFT JOIN email_accounts ea ON ea.id = ue.email_account_id
            WHERE ue.id = ? AND ue.user_id = ?
            """,
            (usable_email_id, user_id),
        ).fetchone()
        if row is None:
            return FetchAccountInfo(email_account_id=None, last_refresh_at=None)
        if row["email_account_id"] is not None:
            return FetchAccountInfo(
                email_account_id=row["email_account_id"],
                last_refresh_at=row["last_refresh_at"],
            )
        base_address = normalize_delivery_address(str(row["address"] or ""))
        if "@" not in base_address:
            return FetchAccountInfo(email_account_id=None, last_refresh_at=None)
        account_rows = conn.execute(
            """
            SELECT ue.email_account_id, ue.address, ea.last_refresh_at
            FROM usable_emails ue
            JOIN email_accounts ea ON ea.id = ue.email_account_id
            WHERE ue.user_id = ? AND ea.user_id = ?
              AND ue.email_account_id IS NOT NULL
            """,
            (user_id, user_id),
        ).fetchall()
    account_row = next(
        (
            direct_row
            for direct_row in account_rows
            if normalize_delivery_address(str(direct_row["address"] or "")) == base_address
        ),
        None,
    )
    if account_row is None:
        return FetchAccountInfo(email_account_id=None, last_refresh_at=None)
    return FetchAccountInfo(
        email_account_id=account_row["email_account_id"],
        last_refresh_at=account_row["last_refresh_at"],
    )


def enrich_fetch_account_info(
    settings: Settings,
    user_id: int,
    items: list[dict[str, object]],
) -> list[dict[str, object]]:
    """批量填充 email_account_id / last_refresh_at (单连接 + 批量查询).

    旧实现逐邮箱调用 resolve_fetch_account_info (每次新开 SQLite 连接 +
    PRAGMA journal_mode=WAL), 5000 邮箱产生 5000+ 次连接争抢进程级锁,
    页面加载慢且并发下间歇 500 (unable to open database file)。
    此处改为单连接两次批量查询 + 内存归一化地址匹配, 语义与旧版完全一致。
    """
    if not items:
        return items
    ids: list[int] = []
    for item in items:
        raw_id: object = item.get("id")
        if isinstance(raw_id, int):
            ids.append(raw_id)
    if not ids:
        for item in items:
            item["email_account_id"] = None
            item["last_refresh_at"] = None
        return items
    unique_ids: list[int] = list(dict.fromkeys(ids))
    placeholders: str = ",".join("?" for _ in unique_ids)
    with connect(settings) as conn:
        # 1) 直接关联: usable_emails.email_account_id -> email_accounts
        direct_rows = conn.execute(
            f"""
            SELECT ue.id, ue.email_account_id, ea.last_refresh_at
            FROM usable_emails ue
            LEFT JOIN email_accounts ea ON ea.id = ue.email_account_id
            WHERE ue.user_id = ? AND ue.id IN ({placeholders})
            """,
            (user_id, *unique_ids),
        ).fetchall()
        # 2) 兜底素材: 该用户全部账号关联邮箱 (一次批量读取),
        #    供无直连账号的邮箱按归一化地址匹配 (语义同旧 resolve_fetch_account_info)
        linked_rows = conn.execute(
            """
            SELECT ue.address, ue.email_account_id, ea.last_refresh_at
            FROM usable_emails ue
            JOIN email_accounts ea ON ea.id = ue.email_account_id
            WHERE ue.user_id = ? AND ue.email_account_id IS NOT NULL
            """,
            (user_id,),
        ).fetchall()
    direct: dict[int, FetchAccountInfo] = {
        int(row["id"]): FetchAccountInfo(
            email_account_id=row["email_account_id"],
            last_refresh_at=row["last_refresh_at"],
        )
        for row in direct_rows
    }
    fallback_by_address: dict[str, FetchAccountInfo] = {}
    for row in linked_rows:
        key: str = normalize_delivery_address(str(row["address"] or ""))
        if key and "@" in key and key not in fallback_by_address:
            fallback_by_address[key] = FetchAccountInfo(
                email_account_id=row["email_account_id"],
                last_refresh_at=row["last_refresh_at"],
            )
    for item in items:
        email_id: object = item.get("id")
        if not isinstance(email_id, int):
            item["email_account_id"] = None
            item["last_refresh_at"] = None
            continue
        info: FetchAccountInfo | None = direct.get(email_id)
        if info is None or info.email_account_id is None:
            address_key: str = normalize_delivery_address(str(item.get("address") or ""))
            if "@" in address_key:
                info = fallback_by_address.get(address_key) or info
        if info is None:
            info = FetchAccountInfo(email_account_id=None, last_refresh_at=None)
        item["email_account_id"] = info.email_account_id
        item["last_refresh_at"] = info.last_refresh_at
    return items


def list_fetch_usable_emails_for_account(
    settings: Settings,
    user_id: int,
    account_id: int,
    *,
    polling_only: bool = False,
) -> list[FetchUsableEmail]:
    with connect(settings) as conn:
        direct_rows = conn.execute(
            """
            SELECT ue.id, ue.address, ue.kind, ea.provider
            FROM usable_emails ue
            JOIN email_accounts ea ON ea.id = ue.email_account_id
            LEFT JOIN groups g ON g.id = COALESCE(ue.group_id, ea.group_id)
                              AND g.user_id = ue.user_id
            WHERE ue.email_account_id = ? AND ue.user_id = ?
              AND ue.status = 'active'
              AND (? = 0 OR COALESCE(g.polling_enabled, 1) = 1)
            """,
            (account_id, user_id, 1 if polling_only else 0),
        ).fetchall()
        standalone_rows = conn.execute(
            """
            SELECT ue.id, ue.address, ue.kind
            FROM usable_emails ue
            LEFT JOIN groups g ON g.id = ue.group_id AND g.user_id = ue.user_id
            WHERE ue.email_account_id IS NULL AND ue.user_id = ? AND ue.status = 'active'
              AND (? = 0 OR COALESCE(g.polling_enabled, 1) = 1)
            """,
            (user_id, 1 if polling_only else 0),
        ).fetchall()
    account_provider: str = str(direct_rows[0]["provider"] or "") if direct_rows else ""
    emails = [
        FetchUsableEmail(
            id=row["id"],
            address=row["address"],
            kind=row["kind"],
            provider=row["provider"],
        )
        for row in direct_rows
    ]
    base_addresses = {normalize_delivery_address(email.address) for email in emails}
    known_ids = {email.id for email in emails}
    for row in standalone_rows:
        address = str(row["address"] or "")
        if normalize_delivery_address(address) not in base_addresses:
            continue
        email_id = int(row["id"])
        if email_id in known_ids:
            continue
        emails.append(
            FetchUsableEmail(
                id=email_id,
                address=address,
                kind=row["kind"],
                provider=account_provider,
            )
        )
        known_ids.add(email_id)
    return emails
