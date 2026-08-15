"""Reachability probes for QQ (NapCat) endpoints used by the login flow."""

from __future__ import annotations

import requests
from hx_email.server.messaging.impl.config import config_str
from hx_email.server.messaging.types import MessagingInstance

PROBE_TIMEOUT: float = 3.0


def probe_qq_login(instance: MessagingInstance) -> dict[str, object]:
    """Check whether the NapCat WebUI and OneBot HTTP API are reachable."""
    webui_url: str = config_str(instance.config, "webui_url")
    api_url: str = config_str(instance.config, "api_base_url")
    webui_ok: bool = _reachable(webui_url)
    api_ok: bool = _reachable(api_url)
    if webui_ok and api_ok:
        message = "NapCat 在线,可以扫码登录"
    elif webui_ok:
        message = "NapCat WebUI 可达,但 OneBot API 不可达,请检查 API 服务端口"
    elif api_ok:
        message = "OneBot API 可达,但 WebUI 不可达,请检查 WebUI 端口 (默认 6099)"
    else:
        message = "NapCat 未启动或地址不可达,请先启动 NapCat 再重试"
    return {
        "webui_reachable": webui_ok,
        "api_reachable": api_ok,
        "webui_url": webui_url,
        "api_base_url": api_url,
        "message": message,
    }


def _reachable(url: str) -> bool:
    if not url:
        return False
    try:
        response: requests.Response = requests.get(url, timeout=PROBE_TIMEOUT)
        return response.status_code < 500
    except requests.RequestException:
        return False
