"""Settings service: domain logic for reading and writing system settings."""

import base64
from typing import Any

from hx_email.config import Settings
from hx_email.database import connect

VERSION: str = "0.1.0"

SETTINGS_DEFAULTS: dict[str, str] = {
    "login_password": "",
    "verification_ai_enabled": "false",
    "verification_ai_base_url": "",
    "verification_ai_model": "",
    "verification_ai_api_key": "",
    "temp_mail_provider": "cloudflare_temp_mail",
    "temp_mail_api_base_url": "",
    "temp_mail_api_key": "",
    "temp_mail_domains": "[]",
    "temp_mail_default_domain": "",
    "temp_mail_prefix_rules": "{}",
    "cf_worker_domains": "[]",
    "cf_worker_default_domain": "",
    "cf_worker_prefix_rules": "{}",
    "cf_worker_base_url": "",
    "cf_worker_admin_key": "",
    "external_api_key": "",
    "external_api_keys": "[]",
    "external_api_public_mode": "false",
    "external_api_ip_whitelist": "[]",
    "external_api_rate_limit_per_minute": "60",
    "external_api_disable_raw_content": "false",
    "external_api_disable_wait_message": "false",
    "pool_external_enabled": "false",
    "enable_scheduled_refresh": "false",
    "refresh_interval_days": "7",
    "refresh_delay_seconds": "2",
    "refresh_cron": "",
    "use_cron_schedule": "false",
    "enable_auto_polling": "false",
    "polling_interval": "30",
    "polling_count": "5",
    "enable_compact_auto_poll": "false",
    "compact_poll_interval": "10",
    "compact_poll_max_count": "3",
    "email_notification_enabled": "false",
    "email_notification_recipient": "",
    "email_notification_smtp_host": "",
    "email_notification_smtp_port": "587",
    "email_notification_smtp_user": "",
    "email_notification_smtp_password": "",
    "webhook_notification_enabled": "false",
    "webhook_notification_url": "",
    "webhook_notification_token": "",
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "telegram_poll_interval": "30",
    "telegram_proxy_url": "",
    "watchtower_url": "",
    "watchtower_token": "",
    "update_method": "watchtower",
    "ui_layout_v2": "{}",
}

SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "verification_ai_api_key",
        "temp_mail_api_key",
        "telegram_bot_token",
        "cf_worker_admin_key",
        "external_api_key",
        "login_password",
        "watchtower_token",
        "email_notification_smtp_password",
    }
)


def encode_value(value: str) -> str:
    """Base64-encode a value for obfuscated storage."""
    if not value:
        return ""
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def decode_value(value: str) -> str:
    """Base64-decode a value from obfuscated storage."""
    if not value:
        return ""
    try:
        return base64.b64decode(value.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return value


def get_setting(settings: Settings, key: str, default: str = "") -> str:
    """Read a single setting, decoding sensitive values transparently."""
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT value FROM system_settings WHERE key = ?",
            (key,),
        ).fetchone()
    if row is None:
        return default
    value: str = str(row["value"])
    if key in SENSITIVE_KEYS:
        return decode_value(value)
    return value


def set_setting(settings: Settings, key: str, value: str) -> None:
    """Write a single setting, encoding sensitive values transparently."""
    stored: str = encode_value(value) if key in SENSITIVE_KEYS else value
    with connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO system_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, stored),
        )


def get_all_settings(settings: Settings) -> dict[str, str]:
    """Return all settings merged with defaults. Sensitive values are decoded."""
    result: dict[str, str] = dict(SETTINGS_DEFAULTS)
    with connect(settings) as connection:
        rows = connection.execute("SELECT key, value FROM system_settings").fetchall()
    for row in rows:
        key: str = row["key"]
        value: str = str(row["value"])
        if key in SETTINGS_DEFAULTS:
            result[key] = decode_value(value) if key in SENSITIVE_KEYS else value
    return result


def update_settings(settings: Settings, updates: dict[str, Any]) -> None:
    """Batch-update settings, encoding sensitive values transparently."""
    with connect(settings) as connection:
        for key, value in updates.items():
            if key not in SETTINGS_DEFAULTS:
                continue
            str_value: str = str(value) if not isinstance(value, str) else value
            stored: str = encode_value(str_value) if key in SENSITIVE_KEYS else str_value
            connection.execute(
                """
                INSERT INTO system_settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, stored),
            )
