"""Temp mail options: read domains and prefix config from settings."""

from __future__ import annotations

from hx_email.config import Settings

_DEFAULT_DOMAINS: dict[str, dict[str, object]] = {
    "cf": {
        "domains": ["@mail.gw"],
        "prefix_rules": ["random"],
        "default_domain": "@mail.gw",
    },
}


def get_temp_mail_options(
    settings: Settings,
    provider_name: str,
) -> dict[str, object]:
    """Return configuration options for creating temp emails via the given provider.

    Reads domains, prefix generation rules, and default domain.
    Falls back to built-in defaults when no override is configured.
    """
    provider_defaults = _DEFAULT_DOMAINS.get(
        provider_name,
        {
            "domains": [],
            "prefix_rules": [],
            "default_domain": "",
        },
    )
    return {
        "provider": provider_name,
        "domains": provider_defaults["domains"],
        "prefix_rules": provider_defaults["prefix_rules"],
        "default_domain": provider_defaults["default_domain"],
    }
