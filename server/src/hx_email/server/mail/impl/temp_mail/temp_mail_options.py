"""Temp mail options: read domains and prefix config from settings.

Also owns the single domain normalization used by every consumer of the CF Worker
domain settings (options filtering, mailbox creation, sync pruning, settings save).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass

from fastapi import HTTPException, status

from hx_email.config import Settings
from hx_email.server.settings_service import get_setting

_DEFAULT_OPTIONS: dict[str, dict[str, object]] = {
    "cf": {
        "domains": [],
        "prefix_rules": ["random"],
        "default_domain": "",
    },
}


class NoUsableTempMailDomainError(HTTPException):
    """No domain may be used for a new mailbox (requested one excluded, or all excluded).

    Raised as a 409 HTTPException: the request is well-formed but conflicts with the
    current domain configuration, and restoring a domain makes the same request succeed.
    It is not a TempMailProviderError, so the API's generic provider 502 mapping stays
    untouched and FastAPI answers 409 with the readable reason in "detail".
    """

    def __init__(self, reason: str) -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=reason)
        self.reason: str = reason


@dataclass(frozen=True)
class CFDomainState:
    """CF Worker domains as stored (display form), filtered by the user's exclusions."""

    synced: list[str]
    usable: list[str]
    excluded: frozenset[str]
    default_domain: str


def normalize_domain(value: str) -> str:
    """Canonical comparison form: trimmed, no leading "@", lowercased; "" when empty."""
    return value.strip().lstrip("@").strip().lower()


def normalize_domains(values: Iterable[object]) -> list[str]:
    """Normalize each domain, drop empty / "@"-only items, dedupe keeping first order."""
    seen: dict[str, None] = {}
    for item in values:
        domain: str = normalize_domain(str(item or ""))
        if domain:
            seen.setdefault(domain, None)
    return list(seen)


def read_domain_list(settings: Settings, key: str) -> list[str]:
    """Read a JSON string-array domain setting; malformed values read as empty."""
    try:
        parsed: object = json.loads(get_setting(settings, key) or "[]")
    except ValueError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item or "").strip()]


def resolve_cf_domains(settings: Settings) -> CFDomainState:
    """Synced domains minus exclusions, plus the default domain that is still usable.

    With synced domains the default must be one of the usable ones, otherwise it falls
    back to the first usable domain ("" when none). Without any synced domain (never
    synced) the configured default is kept unless it is excluded.
    """
    excluded: frozenset[str] = frozenset(
        normalize_domains(read_domain_list(settings, "cf_worker_excluded_domains"))
    )
    synced: dict[str, str] = {}
    for item in read_domain_list(settings, "cf_worker_domains"):
        domain_key: str = normalize_domain(item)
        if domain_key:
            synced.setdefault(domain_key, item)
    usable: dict[str, str] = {k: v for k, v in synced.items() if k not in excluded}
    raw_default: str = (
        get_setting(settings, "cf_worker_default_domain").strip()
        or get_setting(settings, "temp_mail_default_domain").strip()
    )
    preferred: str = normalize_domain(raw_default)
    default_domain: str = ""
    if synced:
        default_domain = usable.get(preferred) or next(iter(usable.values()), "")
    elif preferred and preferred not in excluded:
        default_domain = raw_default
    return CFDomainState(
        synced=list(synced.values()),
        usable=list(usable.values()),
        excluded=excluded,
        default_domain=default_domain,
    )


def resolve_mailbox_domain(settings: Settings, requested_domain: str) -> str:
    """Domain to send to the Worker for a new mailbox; "" lets the Worker choose.

    Raises NoUsableTempMailDomainError when the requested domain is excluded, or when
    no domain was requested and every synced domain is excluded.
    """
    state: CFDomainState = resolve_cf_domains(settings)
    requested_key: str = normalize_domain(requested_domain)
    if requested_key:
        if requested_key in state.excluded:
            raise NoUsableTempMailDomainError(
                f"域名 {requested_key} 已在系统设置-临时邮箱中被删除, 不能用于创建邮箱"
            )
        return requested_key
    if state.default_domain:
        return normalize_domain(state.default_domain)
    if state.synced:
        raise NoUsableTempMailDomainError(
            "CF Worker 已同步的域名都已被删除, 请在系统设置-临时邮箱中恢复至少一个"
        )
    return ""


def get_temp_mail_options(
    settings: Settings,
    provider_name: str,
) -> dict[str, object]:
    """Return configuration options for creating temp emails via the given provider.

    Reads domains, prefix generation rules, and default domain.
    For the "cf" provider, domains come from the synced cf_worker_domains setting
    minus cf_worker_excluded_domains, compared via normalize_domain.
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
        state: CFDomainState = resolve_cf_domains(settings)
        if state.synced:
            domains = state.usable
        default_domain = state.default_domain
    return {
        "provider": provider_name,
        "domains": domains,
        "prefix_rules": provider_defaults["prefix_rules"],
        "default_domain": default_domain,
    }
