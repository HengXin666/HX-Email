"""Group token-status index for patrol views.

Computes, per group and for the ungrouped bucket, how many email accounts
exist and how many of them currently hold a valid OAuth refresh token.
The index is derived live from email_accounts rows, so it stays in sync
with every refresh result without any cache invalidation.
"""

from __future__ import annotations

from dataclasses import dataclass

from hx_email.config import Settings
from hx_email.database import connect

OAUTH_PROVIDERS: frozenset[str] = frozenset({"outlook", "gmail"})


@dataclass(frozen=True)
class TokenBucket:
    """Account and valid-token counts for one group (or the ungrouped bucket)."""

    account_count: int
    oauth_account_count: int
    valid_token_count: int
    invalid_token_count: int


@dataclass(frozen=True)
class GroupTokenStatus:
    id: int
    name: str
    color: str
    proxy_url: str
    allowed_provider: str
    bucket: TokenBucket


@dataclass(frozen=True)
class GroupTokenIndex:
    groups: tuple[GroupTokenStatus, ...]
    ungrouped: TokenBucket


def get_group_token_index(settings: Settings, user_id: int) -> GroupTokenIndex:
    """Build the per-group token status index for the user.

    A token counts as *valid* when the account is an OAuth account
    (outlook/gmail) with a stored refresh token whose latest refresh
    succeeded (refresh_failed_at is NULL and last_refresh_at is set).
    """
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT COALESCE(ea.group_id, 0) AS gid,
                   COUNT(*) AS account_count,
                   SUM(CASE WHEN ea.provider IN ('outlook', 'gmail') THEN 1 ELSE 0 END)
                       AS oauth_account_count,
                   SUM(CASE
                       WHEN ea.provider IN ('outlook', 'gmail')
                        AND ea.refresh_token != ''
                        AND ea.refresh_failed_at IS NULL
                        AND ea.last_refresh_at IS NOT NULL
                       THEN 1 ELSE 0 END) AS valid_token_count,
                   SUM(CASE
                       WHEN ea.provider IN ('outlook', 'gmail')
                        AND ea.refresh_token != ''
                        AND ea.refresh_failed_at IS NOT NULL
                       THEN 1 ELSE 0 END) AS invalid_token_count
            FROM email_accounts ea
            WHERE ea.user_id = ?
            GROUP BY COALESCE(ea.group_id, 0)
            """,
            (user_id,),
        ).fetchall()
        group_rows = connection.execute(
            """
            SELECT id, name, color, proxy_url, allowed_provider
            FROM groups
            WHERE user_id = ?
            ORDER BY sort_order, id
            """,
            (user_id,),
        ).fetchall()

    counts_by_group: dict[int, TokenBucket] = {}
    for row in rows:
        gid: int = int(row["gid"])
        counts_by_group[gid] = TokenBucket(
            account_count=int(row["account_count"]),
            oauth_account_count=int(row["oauth_account_count"]),
            valid_token_count=int(row["valid_token_count"]),
            invalid_token_count=int(row["invalid_token_count"]),
        )

    groups: list[GroupTokenStatus] = []
    for row in group_rows:
        group_id: int = int(row["id"])
        bucket = counts_by_group.get(group_id, TokenBucket(0, 0, 0, 0))
        groups.append(
            GroupTokenStatus(
                id=group_id,
                name=row["name"],
                color=row["color"],
                proxy_url=row["proxy_url"] or "",
                allowed_provider=row["allowed_provider"] or "",
                bucket=bucket,
            )
        )
    ungrouped = counts_by_group.get(0, TokenBucket(0, 0, 0, 0))
    return GroupTokenIndex(groups=tuple(groups), ungrouped=ungrouped)


def export_group_accounts_text(settings: Settings, user_id: int, group_id: int) -> str | None:
    """Export email accounts in a group as tab-separated text."""
    with connect(settings) as connection:
        group_row = connection.execute(
            "SELECT id, name FROM groups WHERE id = ? AND user_id = ?",
            (group_id, user_id),
        ).fetchone()
        if group_row is None:
            return None

        rows = connection.execute(
            """
            SELECT ea.primary_address, ea.provider, ea.display_name, ea.status
            FROM email_accounts ea
            INNER JOIN usable_emails ue
              ON ue.email_account_id = ea.id AND ue.user_id = ea.user_id
            WHERE ea.user_id = ? AND ue.group_id = ?
            ORDER BY ea.id
            """,
            (user_id, group_id),
        ).fetchall()

    lines: list[str] = [
        f"# Group: {group_row['name']}",
        "# Email\tProvider\tDisplay Name\tStatus",
    ]
    for row in rows:
        lines.append(
            "\t".join(
                [
                    row["primary_address"],
                    row["provider"],
                    row["display_name"],
                    row["status"],
                ]
            )
        )
    return "\n".join(lines)
