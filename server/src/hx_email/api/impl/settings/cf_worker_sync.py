"""CF Worker domain sync: pull available domains from each upstream's open_api settings."""

import json
import urllib.error
import urllib.request
from dataclasses import replace
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from hx_email.api.dependencies import require_admin
from hx_email.config import Settings
from hx_email.server.mail.impl.temp_mail.temp_mail_options import (
    normalize_domain,
    normalize_domains,
    resolve_cf_domains,
)
from hx_email.server.mail.impl.temp_mail.upstreams import (
    LEGACY_UPSTREAM_ID,
    UPSTREAMS_KEY,
    CFUpstream,
    dump_upstreams,
    find_upstream,
    read_values,
    upstreams_from_values,
)
from hx_email.server.settings_service import get_setting, set_setting

# Cloudflare bot protection (error 1010) rejects the default Python-urllib
# User-Agent signature, so requests must present a browser-like UA.
_BROWSER_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


class CFWorkerSyncRequest(BaseModel):
    worker_url: str = ""
    admin_key: str = ""
    custom_auth: str = ""
    upstream_id: str = ""


def _json_get(
    url: str, headers: dict[str, str] | None = None, timeout: int = 15
) -> tuple[int, str]:
    """Helper: GET and return (status, body)."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def _parse_domains(data: dict[str, Any]) -> tuple[list[str], str]:
    """Extract (domains, default_domain) from a Worker open_api/settings payload."""
    raw_domains: list[Any] = data.get("domains") or data.get("defaultDomains") or []
    domains: list[str] = [str(d).strip() for d in raw_domains if str(d or "").strip()]
    raw_defaults: list[Any] = data.get("defaultDomains") or []
    default_domain: str = str(raw_defaults[0]).strip() if raw_defaults else ""
    if not default_domain and domains:
        default_domain = domains[0]
    return domains, default_domain


def _fetch_domains(worker_url: str, custom_auth: str) -> tuple[list[str], str, str]:
    """(domains, worker_default, error); error is "" on success."""
    headers: dict[str, str] = dict(_BROWSER_HEADERS)
    if custom_auth:
        # Worker deployed with PASSWORDS (custom auth) requires this on every request
        headers["x-custom-auth"] = custom_auth
    url: str = f"{worker_url.rstrip('/')}/open_api/settings"
    try:
        status_code, body = _json_get(url, headers, timeout=15)
    except Exception as exc:
        return [], "", f"CF Worker 请求失败: {exc}"
    if not 200 <= status_code < 300:
        return [], "", f"CF Worker 查询域名失败 HTTP {status_code}: {body[:200]}"
    try:
        data: Any = json.loads(body)
    except ValueError:
        return [], "", "CF Worker 返回非 JSON 响应, 请检查 Worker URL"
    if not isinstance(data, dict):
        return [], "", "CF Worker 返回结构异常, 请检查 Worker 版本"
    domains, default_domain = _parse_domains(data)
    if not domains:
        return [], "", "CF Worker 未返回任何域名, 请检查 Worker 配置"
    return domains, default_domain, ""


def prune_excluded(excluded: list[str] | tuple[str, ...], domains: list[str]) -> list[str]:
    """Exclusions the Worker still serves, normalized; stale ones would be ghost entries."""
    synced: set[str] = set(normalize_domains(domains))
    return [domain for domain in normalize_domains(excluded) if domain in synced]


def prune_excluded_domains(settings: Settings, domains: list[str]) -> list[str]:
    """Legacy single-Worker keys: drop stale exclusions and persist the rest normalized."""
    try:
        stored: Any = json.loads(get_setting(settings, "cf_worker_excluded_domains") or "[]")
    except ValueError:
        stored = []
    kept: list[str] = prune_excluded(stored if isinstance(stored, list) else [], domains)
    set_setting(settings, "cf_worker_excluded_domains", json.dumps(kept, ensure_ascii=False))
    return kept


def _persist(
    settings: Settings,
    target: CFUpstream,
    domains: list[str],
    is_legacy: bool,
) -> list[str]:
    """Write synced domains into the upstream (legacy keys until the list is first saved)."""
    if is_legacy and target.id == LEGACY_UPSTREAM_ID:
        set_setting(settings, "cf_worker_domains", json.dumps(domains, ensure_ascii=False))
        return prune_excluded_domains(settings, domains)
    upstreams, _legacy = upstreams_from_values(read_values(settings))
    excluded: list[str] = prune_excluded(target.excluded_domains, domains)
    if find_upstream(upstreams, target.id) is None:
        return excluded  # not saved yet: the settings page keeps it until "保存设置"
    updated: list[CFUpstream] = [
        replace(item, domains=tuple(domains), excluded_domains=tuple(excluded))
        if item.id == target.id
        else item
        for item in upstreams
    ]
    set_setting(settings, UPSTREAMS_KEY, dump_upstreams(updated))
    return excluded


def _settle_default(settings: Settings, worker_default: str) -> str:
    """Keep the global default when still usable, else this Worker's default or the first."""
    state = resolve_cf_domains(settings)
    current: str = get_setting(settings, "cf_worker_default_domain")
    if normalize_domain(current) in state.owners:
        return current
    chosen: str = worker_default if normalize_domain(worker_default) in state.owners else ""
    chosen = chosen or state.default_domain
    if chosen:
        set_setting(settings, "cf_worker_default_domain", chosen)
    return chosen


def sync_upstream(
    settings: Settings,
    target: CFUpstream,
    is_legacy: bool,
) -> dict[str, object]:
    """Sync one upstream and return the per-upstream response body."""
    domains, worker_default, error = _fetch_domains(target.base_url, target.custom_auth)
    if error:
        return {"success": False, "upstream_id": target.id, "message": error}
    excluded_domains: list[str] = _persist(settings, target, domains, is_legacy)
    global_default: str = _settle_default(settings, worker_default)
    return {
        "success": True,
        "upstream_id": target.id,
        "domains": domains,
        "default_domain": worker_default,
        "global_default_domain": global_default,
        "excluded_domains": excluded_domains,
        "message": f"已同步 {len(domains)} 个域名",
    }


def resolve_sync_targets(
    payload: CFWorkerSyncRequest,
    upstreams: list[CFUpstream],
    is_legacy: bool,
) -> list[CFUpstream]:
    """Which upstreams this request syncs; unsaved form values override stored ones."""
    worker_url: str = payload.worker_url.strip().rstrip("/")
    wanted_id: str = payload.upstream_id.strip()
    if not wanted_id and worker_url:
        matched: CFUpstream | None = next(
            (item for item in upstreams if item.base_url == worker_url), None
        )
        wanted_id = matched.id if matched else LEGACY_UPSTREAM_ID if is_legacy else ""
    if not wanted_id:
        return [item for item in upstreams if item.enabled and item.base_url]
    stored: CFUpstream = find_upstream(upstreams, wanted_id) or CFUpstream(id=wanted_id)
    return [
        replace(
            stored,
            base_url=worker_url or stored.base_url,
            custom_auth=payload.custom_auth.strip() or stored.custom_auth,
        )
    ]


def register_cf_worker_sync_route(router: APIRouter, settings: Settings) -> None:
    """Register the CF Worker domain sync endpoint (one upstream, or every enabled one).
    .agents/notes/implemented/feature/2026-11-08-temp-mail-multi-upstream.md
    """

    @router.post("/settings/cf-worker-sync-domains")
    def cf_worker_sync_domains(
        payload: CFWorkerSyncRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Sync one upstream (upstream_id / worker_url), or every enabled one when omitted."""
        require_admin(settings, authorization)
        upstreams, is_legacy = upstreams_from_values(read_values(settings))
        targets: list[CFUpstream] = [
            item for item in resolve_sync_targets(payload, upstreams, is_legacy) if item.base_url
        ]
        if not targets:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="worker_url is required"
            )
        results: list[dict[str, object]] = [
            sync_upstream(settings, target, is_legacy) for target in targets
        ]
        if len(results) == 1:
            return results[0]
        succeeded: int = sum(1 for item in results if item["success"])
        return {
            "success": succeeded == len(results),
            "results": results,
            "message": f"已同步 {succeeded}/{len(results)} 个上游",
        }
