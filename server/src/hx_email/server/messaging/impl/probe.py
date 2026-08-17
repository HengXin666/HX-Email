"""QQ engine probe for the login flow (embedded NapCat container)."""

from __future__ import annotations

from hx_email.server.messaging.engine import QQEngineManager, get_engine
from hx_email.server.messaging.types import MessagingInstance


def probe_qq_login(instance: MessagingInstance) -> dict[str, object]:
    """Report whether the embedded NapCat engine is up and its QR is ready."""
    engine: QQEngineManager | None = get_engine(instance.id)
    running: bool = engine is not None and engine.is_running()
    qr_ready: bool = running and engine is not None and engine.qr_image() is not None
    if running and qr_ready:
        message = "QQ 引擎运行中, 可以扫码登录"
    elif running:
        message = "QQ 引擎运行中, 二维码暂未生成"
    else:
        message = "QQ 引擎未启动, 请先点击「启动内置引擎」"
    return {
        "webui_reachable": running,
        "api_reachable": running,
        "webui_url": "",
        "api_base_url": "",
        "message": message,
    }
