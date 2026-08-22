"""Settings service: domain logic for reading and writing system settings."""

import base64
import os
import secrets
from typing import Any

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.security import ENCRYPTED_PREFIX, decrypt_secret, encrypt_secret
from hx_email.server.settings.utils import normalize_external_api_keys
from hx_email.server.settings.validation import validate_callback_url

VERSION: str = os.environ.get("HX_EMAIL_APP_VERSION", "0.8.0")
PROJECT_REPOSITORY_URL: str = "https://github.com/HengXin666/HX-Email"
_SETTING_UPSERT_SQL: str = (
    "INSERT INTO system_settings (key, value) VALUES (?, ?) "
    "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
)

SETTINGS_DEFAULTS: dict[str, str] = {
    "verification_ai_enabled": "false",
    "verification_ai_base_url": "",
    "verification_ai_model": "",
    "verification_ai_api_key": "",
    "cf_worker_domains": "[]",
    "cf_worker_default_domain": "",
    "cf_worker_base_url": "",
    "cf_worker_admin_key": "",
    "cf_worker_custom_auth": "",
    "external_api_key": "",
    "external_api_keys": "[]",
    "external_api_rate_limit_per_minute": "60",
    "external_api_disable_raw_content": "false",
    "external_api_disable_wait_message": "false",
    "pool_external_enabled": "false",
    "enable_auto_polling": "false",
    "polling_interval": "30",
    "refresh_stagger_max_seconds": "20",  # 批量刷新错峰上限(秒)
    "refresh_schedule_enabled": "true",  # 后台定时随机刷新
    "refresh_schedule_interval_seconds": "3600",  # 定时刷新间隔(秒)
    "group_default_proxy_url": "",
    "group_default_notify_enabled": "true",
    "group_default_polling_enabled": "true",
    "email_notification_enabled": "false",
    "email_notification_account_id": "",
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
    "telegram_notification_enabled": "false",
    "telegram_proxy_url": "",
    "script_notification_enabled": "false",
    "script_notification_path": "",
    "script_notification_timeout": "15",
    "ui_layout_v2": "{}",
    "sync_url": "",
    "sync_token": "",
    "sync_interval_seconds": "300",
}

SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "verification_ai_api_key",
        "telegram_bot_token",
        "cf_worker_admin_key",
        "cf_worker_custom_auth",
        "external_api_key",
        "external_api_keys",
        "email_notification_smtp_password",
        "webhook_notification_token",
        "google_oauth_client_secret",
        "sync_token",
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
    decoded_value: str = (
        decrypt_secret(settings, value)
        if key in SENSITIVE_KEYS and value.startswith(ENCRYPTED_PREFIX)
        else decode_value(value)
        if key in SENSITIVE_KEYS
        else value
    )
    if key == "external_api_keys":
        try:
            return normalize_external_api_keys(decoded_value)
        except ValueError:
            return default
    return decoded_value


def set_setting(settings: Settings, key: str, value: str) -> None:
    """Write a single setting, encoding sensitive values transparently."""
    stored: str = encrypt_secret(settings, value) if key in SENSITIVE_KEYS else value
    with connect(settings) as connection:
        connection.execute(_SETTING_UPSERT_SQL, (key, stored))


def get_all_settings(settings: Settings) -> dict[str, str]:
    """Return all settings merged with defaults. Sensitive values are decoded."""
    result: dict[str, str] = dict(SETTINGS_DEFAULTS)
    with connect(settings) as connection:
        rows = connection.execute("SELECT key, value FROM system_settings").fetchall()
    for row in rows:
        key: str = row["key"]
        value: str = str(row["value"])
        if key in SETTINGS_DEFAULTS:
            decoded_value: str = (
                decrypt_secret(settings, value)
                if key in SENSITIVE_KEYS and value.startswith(ENCRYPTED_PREFIX)
                else decode_value(value)
                if key in SENSITIVE_KEYS
                else value
            )
            if key == "external_api_keys":
                try:
                    decoded_value = normalize_external_api_keys(decoded_value)
                except ValueError:
                    decoded_value = SETTINGS_DEFAULTS[key]
            result[key] = decoded_value
    return result


BOOLEAN_SETTING_KEYS: frozenset[str] = frozenset(
    {
        "verification_ai_enabled",
        "external_api_disable_raw_content",
        "external_api_disable_wait_message",
        "pool_external_enabled",
        "enable_auto_polling",
        "refresh_schedule_enabled",
        "group_default_notify_enabled",
        "group_default_polling_enabled",
        "email_notification_enabled",
        "webhook_notification_enabled",
        "telegram_notification_enabled",
        "script_notification_enabled",
    }
)

INTEGER_SETTING_RANGES: dict[str, tuple[int, int]] = {
    "external_api_rate_limit_per_minute": (0, 100_000),
    "polling_interval": (3, 86_400),
    "refresh_schedule_interval_seconds": (60, 86_400),
    "email_notification_smtp_port": (1, 65_535),
    "script_notification_timeout": (1, 300),
}


def stringify_setting_value(value: object) -> str:
    """Convert API values to the canonical string representation used in SQLite."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value).strip() if not isinstance(value, str) else value.strip()


def normalize_settings_updates(
    settings: Settings,
    updates: dict[str, Any],
) -> dict[str, str]:
    """Normalize and validate a partial settings update before persistence."""
    normalized: dict[str, str] = {}
    for key, value in updates.items():
        if key not in SETTINGS_DEFAULTS:
            continue
        string_value: str = (
            normalize_external_api_keys(value)
            if key == "external_api_keys"
            else stringify_setting_value(value)
        )
        if key == "email_notification_account_id" and string_value:
            try:
                account_id: int = int(string_value)
            except ValueError as error:
                raise ValueError("email_notification_account_id must be an integer") from error
            if account_id < 1:
                raise ValueError("email_notification_account_id must be a positive integer")
            string_value = str(account_id)
        if key in BOOLEAN_SETTING_KEYS:
            lowered: str = string_value.lower()
            if lowered not in {"true", "false", "1", "0"}:
                raise ValueError(f"{key} must be true or false")
            string_value = "true" if lowered in {"true", "1"} else "false"
        if key in INTEGER_SETTING_RANGES:
            minimum, maximum = INTEGER_SETTING_RANGES[key]
            try:
                integer_value: int = int(string_value)
            except ValueError as error:
                raise ValueError(f"{key} must be an integer") from error
            if not minimum <= integer_value <= maximum:
                raise ValueError(f"{key} must be between {minimum} and {maximum}")
            string_value = str(integer_value)
        normalized[key] = string_value

    merged: dict[str, str] = {**get_all_settings(settings), **normalized}
    from hx_email.server.sync.config import validate_sync_config

    validate_sync_config(merged)
    webhook_url: str = merged["webhook_notification_url"]
    if webhook_url:
        validate_callback_url(webhook_url, "webhook_notification_url")
    if merged["webhook_notification_enabled"] == "true" and not webhook_url:
        raise ValueError("webhook_notification_url is required when webhook delivery is enabled")
    if merged["email_notification_enabled"] == "true":
        if not merged["email_notification_recipient"]:
            raise ValueError("email_notification_recipient is required for email forwarding")
        if not (merged["email_notification_account_id"] or merged["email_notification_smtp_host"]):
            raise ValueError(
                "email_notification_account_id or email_notification_smtp_host is required"
            )
    if merged["telegram_notification_enabled"] == "true" and (
        not merged["telegram_bot_token"] or not merged["telegram_chat_id"]
    ):
        raise ValueError("telegram_bot_token and telegram_chat_id are required")
    if merged["script_notification_enabled"] == "true":
        script_path: str = merged["script_notification_path"]
        if not script_path or not script_path.lower().endswith(".sh"):
            raise ValueError("script_notification_path must point to a .sh file")
    if merged["pool_external_enabled"] == "true" and not merged["external_api_key"]:
        normalized["external_api_key"] = secrets.token_urlsafe(32)
    return normalized


def update_settings(
    settings: Settings,
    updates: dict[str, Any],
) -> None:
    """Batch-update settings, encoding sensitive values transparently."""
    normalized: dict[str, str] = normalize_settings_updates(settings, updates)
    with connect(settings) as connection:
        for key, str_value in normalized.items():
            stored: str = (
                encrypt_secret(settings, str_value) if key in SENSITIVE_KEYS else str_value
            )
            connection.execute(_SETTING_UPSERT_SQL, (key, stored))
    from hx_email.server.sync.config import apply_sync_config

    apply_sync_config(settings)
    if {"enable_auto_polling", "polling_interval"}.intersection(normalized):
        from hx_email.server.mail.impl.fetch.scheduler import wake_polling_scheduler

        wake_polling_scheduler(settings)
    if {"refresh_schedule_enabled", "refresh_schedule_interval_seconds"}.intersection(normalized):
        from hx_email.server.mail.impl.refresh.settings import wake_refresh_scheduler

        wake_refresh_scheduler(settings)
