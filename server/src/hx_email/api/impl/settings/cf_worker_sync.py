"""CF Worker domain sync: pull available domains from the Worker open_api settings."""

import json
import urllib.error
import urllib.request
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from hx_email.api.dependencies import require_admin
from hx_email.config import Settings
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


def register_cf_worker_sync_route(router: APIRouter, settings: Settings) -> None:
    """Register the CF Worker domain sync endpoint."""

    @router.post("/settings/cf-worker-sync-domains")
    def cf_worker_sync_domains(
        payload: CFWorkerSyncRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Fetch domains from the CF Worker public open_api/settings endpoint and persist them."""
        require_admin(settings, authorization)
        worker_url: str = payload.worker_url or get_setting(settings, "cf_worker_base_url")
        custom_auth: str = payload.custom_auth or get_setting(settings, "cf_worker_custom_auth")
        if not worker_url:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="worker_url is required"
            )
        headers: dict[str, str] = dict(_BROWSER_HEADERS)
        if custom_auth:
            # Worker deployed with PASSWORDS (custom auth) requires this on every request
            headers["x-custom-auth"] = custom_auth
        url: str = f"{worker_url.rstrip('/')}/open_api/settings"
        try:
            status_code, body = _json_get(url, headers, timeout=15)
        except Exception as exc:
            return {"success": False, "message": f"CF Worker 请求失败: {exc}"}
        if not 200 <= status_code < 300:
            return {
                "success": False,
                "message": f"CF Worker 查询域名失败 HTTP {status_code}: {body[:200]}",
            }
        try:
            data: Any = json.loads(body)
        except ValueError:
            return {"success": False, "message": "CF Worker 返回非 JSON 响应, 请检查 Worker URL"}
        if not isinstance(data, dict):
            return {"success": False, "message": "CF Worker 返回结构异常, 请检查 Worker 版本"}
        domains, default_domain = _parse_domains(data)
        if not domains:
            return {"success": False, "message": "CF Worker 未返回任何域名, 请检查 Worker 配置"}
        set_setting(settings, "cf_worker_domains", json.dumps(domains, ensure_ascii=False))
        if default_domain:
            set_setting(settings, "cf_worker_default_domain", default_domain)
        return {
            "success": True,
            "domains": domains,
            "default_domain": default_domain,
            "message": f"已同步 {len(domains)} 个域名",
        }
