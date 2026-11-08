"""CF Worker upstreams: several cloudflare_temp_email Workers behind one "cf" provider.

Stored as the JSON array setting ``cf_worker_upstreams``. Each upstream carries its own
credentials and its own synced / excluded domain lists. Before the first save of that key
the legacy single-Worker keys (``cf_worker_base_url`` ...) are read as one upstream with
id ``default``, so existing installs and existing mailboxes keep working unchanged.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from hx_email.config import Settings
from hx_email.server.mail.temp_mail import MissingTempMailProviderError

UPSTREAMS_KEY: str = "cf_worker_upstreams"
LEGACY_UPSTREAM_ID: str = "default"
LEGACY_CREDENTIAL_KEYS: tuple[str, ...] = (
    "cf_worker_base_url",
    "cf_worker_admin_key",
    "cf_worker_custom_auth",
)
LEGACY_DOMAIN_KEYS: tuple[str, ...] = ("cf_worker_domains", "cf_worker_excluded_domains")


@dataclass(frozen=True)
class CFUpstream:
    """One deployed cloudflare_temp_email Worker."""

    id: str
    name: str = ""
    base_url: str = ""
    admin_key: str = ""
    custom_auth: str = ""
    enabled: bool = True
    domains: tuple[str, ...] = field(default_factory=tuple)
    excluded_domains: tuple[str, ...] = field(default_factory=tuple)

    @property
    def configured(self) -> bool:
        """Has the credentials needed to create a mailbox."""
        return bool(self.base_url and self.admin_key)

    @property
    def label(self) -> str:
        return self.name or self.base_url or self.id

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "base_url": self.base_url,
            "admin_key": self.admin_key,
            "custom_auth": self.custom_auth,
            "enabled": self.enabled,
            "domains": list(self.domains),
            "excluded_domains": list(self.excluded_domains),
        }


def _string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item or "").strip())


def _json_list(raw: str) -> list[Any] | None:
    try:
        parsed: object = json.loads(raw or "[]")
    except ValueError:
        return None
    return parsed if isinstance(parsed, list) else None


def _from_dict(item: Mapping[str, Any]) -> CFUpstream:
    from hx_email.server.mail.impl.temp_mail.temp_mail_options import normalize_domains

    return CFUpstream(
        id=str(item.get("id") or "").strip(),
        name=str(item.get("name") or "").strip(),
        base_url=str(item.get("base_url") or "").strip().rstrip("/"),
        admin_key=str(item.get("admin_key") or "").strip(),
        custom_auth=str(item.get("custom_auth") or "").strip(),
        enabled=item.get("enabled", True) not in (False, "false", 0, "0"),
        domains=_string_list(item.get("domains")),
        excluded_domains=tuple(normalize_domains(_string_list(item.get("excluded_domains")))),
    )


def parse_upstreams(raw: str) -> list[CFUpstream]:
    """Lenient read of the stored value; malformed entries are dropped."""
    items: list[Any] = _json_list(raw) or []
    upstreams: list[CFUpstream] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        upstream: CFUpstream = _from_dict(item)
        if upstream.id and upstream.id not in seen:
            seen.add(upstream.id)
            upstreams.append(upstream)
    return upstreams


def dump_upstreams(upstreams: Iterable[CFUpstream]) -> str:
    return json.dumps([item.to_dict() for item in upstreams], ensure_ascii=False)


def normalize_upstreams_value(raw: str) -> str:
    """Strict validation for PUT /settings; raises ValueError with the key in the message."""
    items: list[Any] | None = _json_list(raw)
    if items is None or not all(isinstance(item, Mapping) for item in items):
        raise ValueError(f"{UPSTREAMS_KEY} must be a JSON array of objects")
    upstreams: list[CFUpstream] = [_from_dict(item) for item in items]
    ids: list[str] = [item.id for item in upstreams]
    if any(not item_id for item_id in ids):
        raise ValueError(f"{UPSTREAMS_KEY}: every upstream needs an id")
    if len(set(ids)) != len(ids):
        raise ValueError(f"{UPSTREAMS_KEY}: upstream ids must be unique")
    for upstream in upstreams:
        if upstream.enabled and not upstream.configured:
            raise ValueError(
                f"{UPSTREAMS_KEY}: 上游 {upstream.label} 已启用, 必须填写 Worker URL 和 Admin Key"
            )
    return dump_upstreams(upstreams)


def legacy_upstream(values: Mapping[str, str]) -> CFUpstream | None:
    """The pre-multi-upstream single Worker, or None when nothing legacy is set."""
    keys: tuple[str, ...] = LEGACY_CREDENTIAL_KEYS + LEGACY_DOMAIN_KEYS
    raw: dict[str, str] = {key: str(values.get(key) or "").strip() for key in keys}
    has_domains: bool = any(_json_list(raw[key]) for key in LEGACY_DOMAIN_KEYS)
    if not any(raw[key] for key in LEGACY_CREDENTIAL_KEYS) and not has_domains:
        return None
    return _from_dict(
        {
            "id": LEGACY_UPSTREAM_ID,
            "base_url": raw["cf_worker_base_url"],
            "admin_key": raw["cf_worker_admin_key"],
            "custom_auth": raw["cf_worker_custom_auth"],
            "domains": _json_list(raw["cf_worker_domains"]) or [],
            "excluded_domains": _json_list(raw["cf_worker_excluded_domains"]) or [],
        }
    )


def upstreams_from_values(values: Mapping[str, str]) -> tuple[list[CFUpstream], bool]:
    """(upstreams, is_legacy): the stored list, else the legacy keys as one upstream."""
    stored: list[CFUpstream] = parse_upstreams(str(values.get(UPSTREAMS_KEY) or ""))
    if stored:
        return stored, False
    legacy: CFUpstream | None = legacy_upstream(values)
    return ([legacy] if legacy else []), True


def read_values(settings: Settings) -> dict[str, str]:
    from hx_email.server.settings_service import get_setting

    keys: tuple[str, ...] = (UPSTREAMS_KEY, *LEGACY_CREDENTIAL_KEYS, *LEGACY_DOMAIN_KEYS)
    return {key: get_setting(settings, key) for key in keys}


def load_upstreams(settings: Settings) -> list[CFUpstream]:
    return upstreams_from_values(read_values(settings))[0]


def find_upstream(upstreams: Iterable[CFUpstream], upstream_id: str) -> CFUpstream | None:
    """Upstream by id; mailboxes and domain owners refer to upstreams only by this id.
    .agents/notes/implemented/feature/2026-11-08-temp-mail-multi-upstream.md
    """
    return next((item for item in upstreams if item.id == upstream_id), None)


def resolve_read_upstream(settings: Settings, upstream_id: str | None) -> CFUpstream:
    """Upstream that owns an existing mailbox. Disabled upstreams can still be read."""
    upstreams: list[CFUpstream] = load_upstreams(settings)
    if upstream_id:
        found: CFUpstream | None = find_upstream(upstreams, upstream_id)
        if found is None:
            raise MissingTempMailProviderError(
                "该临时邮箱所属的 CF Worker 上游已被删除, 请恢复上游配置或删除此邮箱"
            )
    else:
        found = find_upstream(upstreams, LEGACY_UPSTREAM_ID) or next(iter(upstreams), None)
    if found is None or not found.base_url:
        raise MissingTempMailProviderError(
            "CF Worker 未配置: 请在系统设置-临时邮箱中添加至少一个上游"
        )
    return found


def apply_upstreams_fallback(values: dict[str, str]) -> None:
    """GET /settings: expose legacy keys as the upstream list before it is first saved."""
    upstreams, is_legacy = upstreams_from_values(values)
    if is_legacy and upstreams:
        values[UPSTREAMS_KEY] = dump_upstreams(upstreams)


def normalize_temp_mail_updates(normalized: dict[str, str]) -> dict[str, str]:
    """Validate temp mail keys of a settings update; saving upstreams retires legacy keys."""
    from hx_email.server.mail.impl.temp_mail.temp_mail_options import normalize_domain_list

    result: dict[str, str] = dict(normalized)
    if "cf_worker_excluded_domains" in result:
        result["cf_worker_excluded_domains"] = normalize_domain_list(
            "cf_worker_excluded_domains", result["cf_worker_excluded_domains"]
        )
    if UPSTREAMS_KEY in result:
        result[UPSTREAMS_KEY] = normalize_upstreams_value(result[UPSTREAMS_KEY])
        for key in LEGACY_CREDENTIAL_KEYS:
            result[key] = ""
        for key in LEGACY_DOMAIN_KEYS:
            result[key] = "[]"
    return result
