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


def get_account_stats(
    settings: Settings,
    user_id: int,
    provider: str | None = None,
) -> dict[str, object]:
    """账号统计聚合: 仅统计持有授权 token 的 OAuth 账号 (outlook/gmail)。

    可指定 provider (outlook/gmail) 只统计单一服务商; 含凭证状态/分组/存活分布/
    每日新增/每日刷新, 以及按错误码分类的刷新失败原因 (按账号去重)。
    """
    from datetime import UTC, datetime, timedelta

    from hx_email.server.mail.impl.refresh.rounds import get_refresh_round_stats
    from hx_email.server.mail.impl.refresh_log_service import classify_refresh_error

    cutoff_iso: str = (
        (datetime.now(UTC) - timedelta(days=STATS_DAYS))
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
    provider_filter: str = ""
    provider_params: list[object] = []
    if provider:
        provider_filter = " AND ea.provider = ?"
        provider_params.append(provider)
    with connect(settings) as connection:
        rows = connection.execute(
            f"""
            SELECT ea.provider, ea.created_at, ea.refresh_token, ea.refresh_failed_at,
                   ea.last_refresh_at, ea.group_id, g.name AS group_name, g.color AS group_color
            FROM email_accounts ea
            LEFT JOIN groups g ON g.id = ea.group_id
            WHERE ea.user_id = ?
              AND ea.provider IN ('outlook', 'gmail')
              AND ea.refresh_token != ''
              {provider_filter}
            """,
            (user_id, *provider_params),
        ).fetchall()
        refresh_rows = connection.execute(
            f"""
            SELECT rl.status, substr(rl.completed_at, 1, 10) AS day, rl.error_detail,
                   ea.provider
            FROM refresh_logs rl
            JOIN email_accounts ea ON ea.id = rl.account_id AND ea.user_id = ?
            WHERE rl.completed_at >= ?
              {provider_filter}
            """,
            (user_id, cutoff_iso, *provider_params),
        ).fetchall()
        # 错误分类: 取每个账号在窗口内最新一条刷新日志 (按账号去重, 而非日志条数)
        error_rows = connection.execute(
            f"""
            SELECT ea.provider, rl.error_detail
            FROM refresh_logs rl
            JOIN email_accounts ea ON ea.id = rl.account_id AND ea.user_id = ?
            JOIN (
                SELECT account_id, MAX(id) AS max_id
                FROM refresh_logs
                WHERE completed_at >= ?
                GROUP BY account_id
            ) latest ON latest.account_id = rl.account_id AND latest.max_id = rl.id
            WHERE rl.status = 'failed'
              {provider_filter}
            """,
            (user_id, cutoff_iso, *provider_params),
        ).fetchall()
        group_rows = connection.execute(
            "SELECT id, name, color FROM groups WHERE user_id = ? ORDER BY sort_order, id",
            (user_id,),
        ).fetchall()

    total = 0
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
    group_counts: dict[int | None, dict[str, int]] = {}
    daily_new: dict[str, int] = {}
    now: datetime = datetime.now(UTC)
    for row in rows:
        total += 1
        provider_name: str = row["provider"] or ""
        provider_counts[provider_name] = provider_counts.get(provider_name, 0) + 1
        if provider_name == "outlook":
            microsoft += 1
        elif provider_name == "gmail":
            google += 1
        is_valid: bool = row["refresh_failed_at"] is None and row["last_refresh_at"] is not None
        is_invalid: bool = row["refresh_failed_at"] is not None
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
        group_id: int | None = row["group_id"]
        bucket = group_counts.setdefault(group_id, {"total": 0, "valid": 0, "invalid": 0})
        bucket["total"] += 1
        if is_valid:
            bucket["valid"] += 1
        elif is_invalid:
            bucket["invalid"] += 1
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
    error_counts: dict[tuple[str, str], int] = {}
    error_labels: dict[tuple[str, str], str] = {}
    for row in refresh_rows:
        day_val: str = row["day"] or ""
        if day_val in daily_refresh:
            status_v: str = row["status"] or ""
            if status_v == "success":
                daily_refresh[day_val]["success"] += 1
            elif status_v == "failed":
                daily_refresh[day_val]["failed"] += 1
    for row in error_rows:
        provider_v: str = row["provider"] or ""
        category, label = classify_refresh_error(provider_v, row["error_detail"] or "")
        key = (provider_v, category)
        error_counts[key] = error_counts.get(key, 0) + 1
        error_labels[key] = label

    groups_out: list[dict[str, object]] = []
    for group_row in group_rows:
        gid: int = int(group_row["id"])
        bucket = group_counts.get(gid, {"total": 0, "valid": 0, "invalid": 0})
        if bucket["total"] == 0:
            continue  # 空分组不展示
        groups_out.append(
            {
                "group_id": gid,
                "name": group_row["name"],
                "color": group_row["color"],
                **bucket,
            }
        )
    ungrouped = group_counts.get(None, {"total": 0, "valid": 0, "invalid": 0})

    return {
        "total": total,
        "oauth": total,
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
        "by_group": groups_out,
        "ungrouped": ungrouped,
        "error_categories": [
            {"provider": key[0], "category": key[1], "label": error_labels[key], "count": count}
            for key, count in sorted(error_counts.items(), key=lambda item: -item[1])
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
        "refresh_rounds": get_refresh_round_stats(settings, user_id, provider, cutoff_iso),
    }
