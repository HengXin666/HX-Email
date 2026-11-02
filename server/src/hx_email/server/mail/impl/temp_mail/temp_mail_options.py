"""Temp mail options: read domains and prefix config from settings."""

from __future__ import annotations

import json

from hx_email.config import Settings
from hx_email.server.settings_service import get_setting

_DEFAULT_OPTIONS: dict[str, dict[str, object]] = {
    "cf": {
        "domains": [],
        "prefix_rules": ["random"],
        "default_domain": "",
    },
}


def read_domain_list(settings: Settings, key: str) -> list[str]:
    """Read a JSON string-array domain setting; malformed values read as empty."""
    try:
        parsed: object = json.loads(get_setting(settings, key) or "[]")
    except ValueError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item or "").strip()]


def get_temp_mail_options(
    settings: Settings,
    provider_name: str,
) -> dict[str, object]:
    """Return configuration options for creating temp emails via the given provider.

    Reads domains, prefix generation rules, and default domain.
    For the "cf" provider, domains come from the synced cf_worker_domains setting
    minus cf_worker_excluded_domains (compared without the leading "@").
    """
    provider_defaults: dict[str, object] = _DEFAULT_OPTIONS.get(
        provider_name,
        {
            "domains": [],
            "prefix_rules": [],
            "default_domain": "",
        },
    )
    domains: object = provider_defaults["domains"]
    default_domain: object = provider_defaults["default_domain"]
    if provider_name == "cf":
        synced_domains: list[str] = read_domain_list(settings, "cf_worker_domains")
        excluded: set[str] = {
            item.lstrip("@") for item in read_domain_list(settings, "cf_worker_excluded_domains")
        }
        usable_domains: list[str] = [
            item for item in synced_domains if item.lstrip("@") not in excluded
        ]
        if synced_domains:
            domains = usable_domains
        synced_default: str = (
            get_setting(settings, "cf_worker_default_domain").strip()
            or get_setting(settings, "temp_mail_default_domain").strip()
        )
        if synced_default and synced_default.lstrip("@") not in excluded:
            default_domain = synced_default
        elif synced_domains:
            default_domain = usable_domains[0] if usable_domains else ""
    return {
        "provider": provider_name,
        "domains": domains,
        "prefix_rules": provider_defaults["prefix_rules"],
        "default_domain": default_domain,
    }
