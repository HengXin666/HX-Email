"""System service: health, capabilities, and account status for external API."""

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.settings_service import VERSION, get_setting


def get_health(settings: Settings) -> dict[str, str]:
    """Return service health: {"status": "ok", "version": "..."}."""
    return {"status": "ok", "version": VERSION}


def get_capabilities(settings: Settings) -> dict[str, object]:
    """Return enabled features based on settings.

    Checks pool_external_enabled, external_api_disable_raw_content,
    external_api_disable_wait_message, etc.
    """
    pool_enabled: str = get_setting(settings, "pool_external_enabled", "false")
    disable_raw: str = get_setting(settings, "external_api_disable_raw_content", "false")
    disable_wait: str = get_setting(settings, "external_api_disable_wait_message", "false")
    ai_enabled: str = get_setting(settings, "verification_ai_enabled", "false")
    rate_limit: str = get_setting(settings, "external_api_rate_limit_per_minute", "60")

    return {
        "pool_enabled": pool_enabled == "true",
        "raw_content_enabled": disable_raw != "true",
        "wait_message_enabled": disable_wait != "true",
        "verification_ai_enabled": ai_enabled == "true",
        "rate_limit_per_minute": int(rate_limit) if rate_limit.isdigit() else 60,
        "version": VERSION,
    }


def get_account_status(settings: Settings, email: str) -> dict[str, object]:
    """Return status of an email account: exists, active/inactive, in pool, etc."""
    result: dict[str, object] = {
        "email": email,
        "exists": False,
        "active": False,
        "in_pool": False,
        "pool_status": "",
        "provider": "",
    }
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT ue.id AS usable_email_id, ue.address, ue.status AS ue_status,
                   ea.provider,
                   mpe.status AS pool_status
            FROM usable_emails ue
            LEFT JOIN email_accounts ea ON ea.id = ue.email_account_id
            LEFT JOIN mail_pool_entries mpe ON mpe.usable_email_id = ue.id
            WHERE LOWER(ue.address) = LOWER(?)
            """,
            (email,),
        ).fetchone()
        if row is None:
            return result
        result["exists"] = True
        result["active"] = row["ue_status"] == "active"
        result["provider"] = str(row["provider"] or "")
        pool_status: str = str(row["pool_status"] or "")
        result["in_pool"] = bool(pool_status)
        result["pool_status"] = pool_status
    return result
