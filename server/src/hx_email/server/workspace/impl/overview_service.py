"""Overview statistics service with 30-second TTL caching.

Provides system-wide aggregated stats for the admin dashboard.
All functions return dict[str, object] for direct JSON serialization.
"""

from __future__ import annotations

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.workspace.impl.overview_cache import (
    _get_cached,
    _set_cached,
)


def get_overview_summary(settings: Settings) -> dict[str, object]:
    """Aggregated system overview counts across all users."""
    cache_key = "overview_summary"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    with connect(settings) as connection:
        total_users = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_accounts = connection.execute("SELECT COUNT(*) FROM email_accounts").fetchone()[0]
        active_accounts = connection.execute(
            "SELECT COUNT(*) FROM email_accounts WHERE status = 'active'"
        ).fetchone()[0]
        total_usable_emails = connection.execute("SELECT COUNT(*) FROM usable_emails").fetchone()[0]
        active_usable_emails = connection.execute(
            "SELECT COUNT(*) FROM usable_emails WHERE active = 1"
        ).fetchone()[0]
        temp_mail_count = connection.execute("SELECT COUNT(*) FROM temp_mailboxes").fetchone()[0]
        platform_count = connection.execute("SELECT COUNT(*) FROM platforms").fetchone()[0]
        binding_count = connection.execute("SELECT COUNT(*) FROM platform_bindings").fetchone()[0]

    result: dict[str, object] = {
        "total_users": total_users,
        "total_accounts": total_accounts,
        "active_accounts": active_accounts,
        "total_usable_emails": total_usable_emails,
        "active_usable_emails": active_usable_emails,
        "temp_mail_count": temp_mail_count,
        "platform_count": platform_count,
        "binding_count": binding_count,
    }
    _set_cached(cache_key, result)
    return result


def get_verification_stats(settings: Settings) -> dict[str, object]:
    """Verification code extraction statistics."""
    cache_key = "verification_stats"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    with connect(settings) as connection:
        total = connection.execute("SELECT COUNT(*) FROM verification_readings").fetchone()[0]
        codes_extracted = connection.execute(
            "SELECT COUNT(*) FROM verification_readings WHERE code IS NOT NULL"
        ).fetchone()[0]
        links_extracted = connection.execute(
            "SELECT COUNT(*) FROM verification_readings WHERE link IS NOT NULL"
        ).fetchone()[0]
        certain_count = connection.execute(
            "SELECT COUNT(*) FROM verification_readings WHERE certainty = 'certain'"
        ).fetchone()[0]

    success_rate: float = (codes_extracted / total * 100) if total > 0 else 0.0

    result: dict[str, object] = {
        "total_extractions": total,
        "codes_extracted": codes_extracted,
        "links_extracted": links_extracted,
        "certain_matches": certain_count,
        "success_rate": round(success_rate, 1),
        "average_latency_ms": 0,
    }
    _set_cached(cache_key, result)
    return result


def get_external_api_stats(settings: Settings) -> dict[str, object]:
    """External API call statistics (OAuth refresh logs)."""
    cache_key = "external_api_stats"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    with connect(settings) as connection:
        total_calls = connection.execute("SELECT COUNT(*) FROM refresh_logs").fetchone()[0]
        success_calls = connection.execute(
            "SELECT COUNT(*) FROM refresh_logs WHERE status = 'success'"
        ).fetchone()[0]
        failed_calls = connection.execute(
            "SELECT COUNT(*) FROM refresh_logs WHERE status = 'failed'"
        ).fetchone()[0]
        active_keys = connection.execute(
            "SELECT COUNT(*) FROM email_accounts WHERE client_id != '' AND status = 'active'"
        ).fetchone()[0]
        last_call_row = connection.execute(
            "SELECT created_at FROM refresh_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()

    result: dict[str, object] = {
        "total_api_calls": total_calls,
        "success_calls": success_calls,
        "failed_calls": failed_calls,
        "active_keys": active_keys,
        "last_call_at": last_call_row["created_at"] if last_call_row is not None else "",
    }
    _set_cached(cache_key, result)
    return result


def get_pool_stats(settings: Settings) -> dict[str, object]:
    """Mail pool status distribution statistics."""
    cache_key = "pool_stats"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    statuses = ("available", "claimed", "completed", "cooling", "frozen", "retired")
    with connect(settings) as connection:
        counts: dict[str, int] = {}
        for status in statuses:
            row = connection.execute(
                "SELECT COUNT(*) FROM mail_pool_entries WHERE status = ?",
                (status,),
            ).fetchone()
            counts[status] = row[0]
        total_pool = sum(counts.values())

    result: dict[str, object] = {
        "total_in_pool": total_pool,
        "available": counts["available"],
        "claimed": counts["claimed"],
        "completed": counts["completed"],
        "cooling": counts["cooling"],
        "frozen": counts["frozen"],
        "retired": counts["retired"],
    }
    _set_cached(cache_key, result)
    return result


def get_activity_stats(settings: Settings) -> dict[str, object]:
    """System activity summary from audit logs."""
    cache_key = "activity_stats"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    with connect(settings) as connection:
        total_actions = connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        recent_rows = connection.execute(
            """
            SELECT action, COUNT(*) AS cnt
            FROM audit_logs
            GROUP BY action
            ORDER BY cnt DESC
            LIMIT 10
            """
        ).fetchall()
        last_entry_row = connection.execute(
            "SELECT created_at FROM audit_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()

    result: dict[str, object] = {
        "total_actions": total_actions,
        "top_actions": [{"action": row["action"], "count": row["cnt"]} for row in recent_rows],
        "last_activity": (last_entry_row["created_at"] if last_entry_row is not None else ""),
    }
    _set_cached(cache_key, result)
    return result
