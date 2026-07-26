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


def _read_synced_domains(settings: Settings) -> list[str]:
    try:
        parsed: object = json.loads(get_setting(settings, "cf_worker_domains") or "[]")
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
    For the "cf" provider, domains come from the synced cf_worker_domains setting.
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
        synced_domains: list[str] = _read_synced_domains(settings)
        if synced_domains:
            domains = synced_domains
        synced_default: str = (
            get_setting(settings, "cf_worker_default_domain").strip()
            or get_setting(settings, "temp_mail_default_domain").strip()
        )
        if synced_default:
            default_domain = synced_default
        elif synced_domains:
            default_domain = synced_domains[0]
    return {
        "provider": provider_name,
        "domains": domains,
        "prefix_rules": provider_defaults["prefix_rules"],
        "default_domain": default_domain,
    }
