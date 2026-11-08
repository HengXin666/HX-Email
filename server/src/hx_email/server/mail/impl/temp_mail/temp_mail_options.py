"""Temp mail options: read domains and prefix config from settings.

Also owns the single domain normalization used by every consumer of the CF Worker
domain settings (options filtering, mailbox creation, sync pruning, settings save), and
the domain -> upstream routing used when a mailbox is created.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field

from fastapi import HTTPException, status

from hx_email.config import Settings
from hx_email.server.mail.impl.temp_mail.upstreams import CFUpstream, find_upstream, load_upstreams
from hx_email.server.mail.temp_mail import MissingTempMailProviderError
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
    """CF Worker domains across enabled upstreams (display form), minus the exclusions.

    ``owners`` maps each usable normalized domain to the id of the first enabled upstream
    that serves it; upstream order is the tie-breaker when two Workers share a domain.
    """

    synced: list[str]
    usable: list[str]
    excluded: frozenset[str]
    default_domain: str
    owners: dict[str, str] = field(default_factory=dict)


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


def normalize_domain_list(key: str, value: str) -> str:
    """Strict PUT /settings validation of a JSON string-array domain setting."""
    try:
        parsed: object = json.loads(value or "[]")
    except ValueError:
        parsed = None
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError(f"{key} must be a JSON array of strings")
    return json.dumps(normalize_domains(parsed), ensure_ascii=False)


def resolve_cf_domains(settings: Settings) -> CFDomainState:
    """Union of every enabled upstream's synced domains minus its own exclusions.

    With synced domains the default must be one of the usable ones, otherwise it falls
    back to the first usable domain ("" when none). Without any synced domain (never
    synced) the configured default is kept unless it is excluded.
    """
    synced: dict[str, str] = {}
    usable: dict[str, str] = {}
    owners: dict[str, str] = {}
    excluded_any: set[str] = set()
    for upstream in load_upstreams(settings):
        if not upstream.enabled:
            continue
        own_excluded: set[str] = set(normalize_domains(upstream.excluded_domains))
        excluded_any |= own_excluded
        for item in upstream.domains:
            domain_key: str = normalize_domain(item)
            if not domain_key:
                continue
            synced.setdefault(domain_key, item)
            if domain_key not in own_excluded and domain_key not in owners:
                owners[domain_key] = upstream.id
                usable[domain_key] = item
    excluded: frozenset[str] = frozenset(excluded_any - set(usable))
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
        owners=owners,
    )


def resolve_mailbox_domain(state: CFDomainState, requested_domain: str) -> str:
    """Domain to send to the Worker for a new mailbox; "" lets the Worker choose.

    Raises NoUsableTempMailDomainError when the requested domain is excluded, or when
    no domain was requested and every synced domain is excluded.
    """
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


def resolve_mailbox_target(settings: Settings, requested_domain: str) -> tuple[CFUpstream, str]:
    """(upstream, domain) for a new mailbox: the domain decides which Worker creates it."""
    upstreams: list[CFUpstream] = load_upstreams(settings)
    configured: list[CFUpstream] = [item for item in upstreams if item.enabled and item.configured]
    if not configured:
        raise MissingTempMailProviderError(
            "CF Worker 未配置: 请在系统设置-临时邮箱中填写 Worker URL 和 Admin Key"
        )
    state: CFDomainState = resolve_cf_domains(settings)
    domain: str = resolve_mailbox_domain(state, requested_domain)
    owner_id: str | None = state.owners.get(domain)
    if owner_id is not None:
        owner: CFUpstream | None = find_upstream(configured, owner_id)
        if owner is None:
            raise MissingTempMailProviderError(
                f"提供域名 {domain} 的上游未填写 Worker URL 或 Admin Key"
            )
        return owner, domain
    if domain and any(domain in normalize_domains(item.domains) for item in upstreams):
        raise NoUsableTempMailDomainError(f"提供域名 {domain} 的上游已停用, 不能用于创建邮箱")
    if not domain or len(configured) == 1:
        return configured[0], domain
    raise NoUsableTempMailDomainError(
        f"没有任何已启用的上游提供域名 {domain}, 请先在系统设置-临时邮箱中同步域名"
    )


def get_temp_mail_options(
    settings: Settings,
    provider_name: str,
) -> dict[str, object]:
    """Return configuration options for creating temp emails via the given provider.

    Reads domains, prefix generation rules, and default domain.
    For the "cf" provider, domains are the union of every enabled upstream's synced
    domains minus that upstream's exclusions, compared via normalize_domain.
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
