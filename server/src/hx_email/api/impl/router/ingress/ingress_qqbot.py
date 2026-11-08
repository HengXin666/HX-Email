"""QQ 官方机器人回调端点: POST /api/v1/router/ingress/qqbot/{instance_id}.

op 13 (回调地址验证) 直接签名回包; 其余先验 Ed25519 签名, 再把子频道消息同步入库并唤醒订阅,
最后回 op 12 表示已收到. 消息量小 (公域只推 @ 机器人的消息), 不另起队列.
"""

from __future__ import annotations

import json

import anyio
from fastapi import APIRouter, HTTPException, Request, status

from hx_email.config import Settings
from hx_email.server.gateway.listen import store_envelopes
from hx_email.server.gateway.providers import HUB, InstanceRow, load_instance
from hx_email.server.router.providers.impl.qqbot.qqbot_events import (
    OP_ACK,
    OP_VALIDATE,
    as_dict,
)
from hx_email.server.router.providers.qqbot import QQBotProvider

ROUTER_PREFIX: str = "/api/v1/router"
INGRESS_PATH: str = "/ingress/qqbot/{instance_id}"


def provider_of(settings: Settings, instance_id: int) -> QQBotProvider:
    instance: InstanceRow | None = load_instance(settings, instance_id)
    if instance is None or instance.kind != "qqbot":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown QQ bot instance")
    provider = HUB.provider_for(settings, instance)
    if not isinstance(provider, QQBotProvider):  # pragma: no cover - HUB builds by kind
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown QQ bot instance")
    return provider


# 回调地址验证不带签名, 只能按平台规则直接回签; 事件推送一律先验签再入库
# 决策记录: .agents/notes/implemented/feature/2026-11-09-qqbot-guild.md
def build_qqbot_ingress_router(settings: Settings) -> APIRouter:
    router: APIRouter = APIRouter(prefix=ROUTER_PREFIX)

    @router.post(INGRESS_PATH)
    async def receive_qqbot_event(instance_id: int, request: Request) -> dict[str, object]:
        body: bytes = await request.body()
        provider: QQBotProvider = await anyio.to_thread.run_sync(provider_of, settings, instance_id)
        try:
            payload: dict[str, object] = as_dict(json.loads(body))
        except (ValueError, UnicodeDecodeError) as error:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON body") from error
        if payload.get("op") == OP_VALIDATE:
            return dict(provider.validation_reply(as_dict(payload.get("d"))))
        if not provider.verify_event(instance_id, dict(request.headers), body):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")
        envelopes: list[dict[str, object]] = provider.parse_event(
            instance_id, dict(request.headers), body
        )
        if envelopes:
            # 入库是同步 SQLite 写, 放到线程里, 不占事件循环
            await anyio.to_thread.run_sync(store_envelopes, settings, instance_id, envelopes)
        return {"op": OP_ACK, "d": 0}

    return router
