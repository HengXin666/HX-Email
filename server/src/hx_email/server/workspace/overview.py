from dataclasses import dataclass
from sqlite3 import Connection

from hx_email.config import Settings
from hx_email.database import connect


@dataclass(frozen=True)
class WorkbenchOverview:
    usable_email_count: int
    active_email_count: int
    account_count: int
    temp_email_count: int
    platform_count: int
    binding_count: int
    pool_available_count: int
    pool_claimed_count: int
    verification_count: int


def get_workbench_overview(settings: Settings, user_id: int) -> WorkbenchOverview:
    with connect(settings) as connection:
        usable_email_count = count_rows(connection, "usable_emails", user_id)
        active_email_count = count_rows(connection, "usable_emails", user_id, "status = 'active'")
        account_count = count_rows(connection, "email_accounts", user_id)
        temp_email_count = count_rows(connection, "temp_mailboxes", user_id)
        platform_count = count_rows(connection, "platforms", user_id)
        binding_count = count_rows(connection, "platform_bindings", user_id)
        pool_available_count = count_rows(
            connection, "mail_pool_entries", user_id, "status = 'available'"
        )
        pool_claimed_count = count_rows(
            connection, "mail_pool_entries", user_id, "status = 'claimed'"
        )
        verification_count = count_rows(connection, "verification_readings", user_id)

    return WorkbenchOverview(
        usable_email_count=usable_email_count,
        active_email_count=active_email_count,
        account_count=account_count,
        temp_email_count=temp_email_count,
        platform_count=platform_count,
        binding_count=binding_count,
        pool_available_count=pool_available_count,
        pool_claimed_count=pool_claimed_count,
        verification_count=verification_count,
    )


def count_rows(
    connection: Connection,
    table: str,
    user_id: int,
    condition: str | None = None,
) -> int:
    where = "user_id = ?"
    if condition is not None:
        where = f"{where} AND {condition}"
    row = connection.execute(
        f"SELECT COUNT(*) FROM {table} WHERE {where}",
        (user_id,),
    ).fetchone()
    return int(row[0])


# 存活天数分档: (标签, 最小天数, 最大天数含上限, None 表示无上限)
AGE_BUCKETS: tuple[tuple[str, int, int | None], ...] = (
    ("<7天", 0, 7),
    ("7-14天", 7, 14),
    ("14-30天", 14, 30),
    ("30-60天", 30, 60),
    ("60-90天", 60, 90),
    ("90-180天", 90, 180),
    ("180天+", 180, None),
)
OAUTH_PROVIDERS: frozenset[str] = frozenset({"outlook", "gmail"})
STATS_DAYS: int = 30


def day_key(value: str) -> str:
    return value[:10]


def get_account_stats(settings: Settings, user_id: int) -> dict[str, object]:
    """账号统计聚合: 总数/凭证状态/服务商分布/存活分布/每日新增/每日刷新。

    供账号统计页 (折线图 + 分布图) 使用, 一次性返回全部聚合, 避免客户端分页遗漏。
    """
    from datetime import UTC, datetime, timedelta

    cutoff_iso: str = (
        (datetime.now(UTC) - timedelta(days=STATS_DAYS))
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT provider, created_at, refresh_token, refresh_failed_at, last_refresh_at
            FROM email_accounts
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchall()
        refresh_rows = connection.execute(
            """
            SELECT rl.status, substr(rl.completed_at, 1, 10) AS day
            FROM refresh_logs rl
            JOIN email_accounts ea ON ea.id = rl.account_id AND ea.user_id = ?
            WHERE rl.completed_at >= ?
            """,
            (user_id, cutoff_iso),
        ).fetchall()

    total = 0
    oauth = 0
    microsoft = 0
    google = 0
    valid = 0
    invalid = 0
    unknown = 0
    failed_refresh = 0
    last_refresh: str | None = None
    bucket_counts: list[dict[str, int]] = [
        {"valid": 0, "invalid": 0, "unknown": 0} for _ in AGE_BUCKETS
    ]
    provider_counts: dict[str, int] = {}
    daily_new: dict[str, int] = {}
    now: datetime = datetime.now(UTC)
    for row in rows:
        total += 1
        provider: str = row["provider"] or ""
        provider_counts[provider] = provider_counts.get(provider, 0) + 1
        if provider == "outlook":
            microsoft += 1
        elif provider == "gmail":
            google += 1
        if provider in OAUTH_PROVIDERS:
            oauth += 1
        has_token: bool = bool(row["refresh_token"])
        is_valid: bool = (
            provider in OAUTH_PROVIDERS
            and has_token
            and row["refresh_failed_at"] is None
            and row["last_refresh_at"] is not None
        )
        is_invalid: bool = (
            provider in OAUTH_PROVIDERS and has_token and row["refresh_failed_at"] is not None
        )
        if is_valid:
            valid += 1
        elif is_invalid:
            invalid += 1
        else:
            unknown += 1
        if row["refresh_failed_at"] is not None:
            failed_refresh += 1
        if row["last_refresh_at"] and (
            last_refresh is None or row["last_refresh_at"] > last_refresh
        ):
            last_refresh = row["last_refresh_at"]
        created_at: str = row["created_at"] or ""
        if created_at:
            day: str = day_key(created_at)
            daily_new[day] = daily_new.get(day, 0) + 1
            try:
                created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                age_days: int = max(0, (now - created).days)
            except ValueError:
                age_days = -1
            if age_days >= 0:
                for index, (_label, min_days, max_days) in enumerate(AGE_BUCKETS):
                    if age_days >= min_days and (max_days is None or age_days < max_days):
                        if is_valid:
                            bucket_counts[index]["valid"] += 1
                        elif is_invalid:
                            bucket_counts[index]["invalid"] += 1
                        else:
                            bucket_counts[index]["unknown"] += 1
                        break

    days: list[str] = []
    for offset in range(STATS_DAYS - 1, -1, -1):
        days.append((now - timedelta(days=offset)).strftime("%Y-%m-%d"))
    daily_refresh: dict[str, dict[str, int]] = {day: {"success": 0, "failed": 0} for day in days}
    for row in refresh_rows:
        day_val: str = row["day"] or ""
        if day_val in daily_refresh:
            status_v: str = row["status"] or ""
            if status_v == "success":
                daily_refresh[day_val]["success"] += 1
            elif status_v == "failed":
                daily_refresh[day_val]["failed"] += 1

    return {
        "total": total,
        "oauth": oauth,
        "microsoft": microsoft,
        "google": google,
        "valid": valid,
        "invalid": invalid,
        "unknown": unknown,
        "failed_refresh": failed_refresh,
        "last_refresh": last_refresh,
        "by_provider": [
            {"provider": provider, "count": count}
            for provider, count in sorted(provider_counts.items(), key=lambda item: -item[1])
        ],
        "age_buckets": [
            {
                "label": label,
                "min": min_days,
                "max": max_days,
                **bucket_counts[index],
            }
            for index, (label, min_days, max_days) in enumerate(AGE_BUCKETS)
        ],
        "daily_new": [{"date": day, "count": daily_new.get(day, 0)} for day in days],
        "daily_refresh": [{"date": day, **daily_refresh[day]} for day in days],
    }
