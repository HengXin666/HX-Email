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
    for item in items:
        usable_email_id = item.get("id")
        if not isinstance(usable_email_id, int):
            item["email_account_id"] = None
            item["last_refresh_at"] = None
            continue
        info = resolve_fetch_account_info(settings, user_id, usable_email_id)
        item["email_account_id"] = info.email_account_id
        item["last_refresh_at"] = info.last_refresh_at
    return items


def list_fetch_usable_emails_for_account(
    settings: Settings,
    user_id: int,
    account_id: int,
) -> list[FetchUsableEmail]:
    with connect(settings) as conn:
        direct_rows = conn.execute(
            """
            SELECT ue.id, ue.address, ue.kind, ea.provider
            FROM usable_emails ue
            JOIN email_accounts ea ON ea.id = ue.email_account_id
            WHERE ue.email_account_id = ? AND ue.user_id = ?
            """,
            (account_id, user_id),
        ).fetchall()
        standalone_rows = conn.execute(
            """
            SELECT id, address, kind
            FROM usable_emails
            WHERE email_account_id IS NULL AND user_id = ? AND status = 'active'
            """,
            (user_id,),
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
