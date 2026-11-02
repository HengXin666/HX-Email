"""GitHub webhook 接收端点: POST /api/v1/router/ingress/github/{instance_id}.

同步路径只做签名校验, JSON 校验, 投递去重与入队, 秒级返回.
映射与落库在 IngressWorker 线程里异步完成.
状态码按 docs/providers/github-app.md 第 5.4 节: 入队 202, 重复 200, 签名错 401, 未处理事件 204.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Protocol

from fastapi import APIRouter, HTTPException, Request, Response, status

from hx_email.api.impl.router.ingress_queue import DeliveryLedger, IngressJob, IngressWorker
from hx_email.server.router.providers.impl.github.github_events import (
    DELIVERY_HEADER,
    EVENT_HEADER,
    HANDLED_EVENTS,
    lower_headers,
)

ROUTER_PREFIX: str = "/api/v1/router"
INGRESS_PATH: str = "/ingress/github/{instance_id}"


class WebhookVerifier(Protocol):
    def verify_event(self, instance_id: int, headers: dict[str, str], body: bytes) -> bool: ...


InstanceExists = Callable[[int], bool]


def register_github_ingress_routes(
    router: APIRouter,
    verifier: WebhookVerifier,
    ledger: DeliveryLedger,
    worker: IngressWorker,
    instance_exists: InstanceExists,
) -> None:
    @router.post(INGRESS_PATH, status_code=status.HTTP_202_ACCEPTED)
    async def receive_github_event(instance_id: int, request: Request) -> Response:
        body: bytes = await request.body()
        headers: dict[str, str] = lower_headers(dict(request.headers))
        if not instance_exists(instance_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown GitHub instance")
        if not verifier.verify_event(instance_id, headers, body):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")
        try:
            payload: object = json.loads(body)
        except (ValueError, UnicodeDecodeError) as error:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON body") from error
        if not isinstance(payload, dict):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Webhook body must be an object")
        delivery_id: str = headers.get(DELIVERY_HEADER, "").strip()
        if not delivery_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing X-GitHub-Delivery")
        event: str = headers.get(EVENT_HEADER, "")
        if event == "ping":
            return Response(status_code=status.HTTP_200_OK)
        if event not in HANDLED_EVENTS:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        if not ledger.claim(instance_id, delivery_id, event):
            return Response(status_code=status.HTTP_200_OK)
        worker.submit(IngressJob(instance_id, delivery_id, headers, body))
        return Response(status_code=status.HTTP_202_ACCEPTED)


# 路由层订阅与分发的决策记录, 实现规格见 docs/messaging-router.md
# .agents/notes/implemented/feature/2026-11-02-messaging-router-gateway.md
def build_github_ingress_router(
    verifier: WebhookVerifier,
    ledger: DeliveryLedger,
    worker: IngressWorker,
    instance_exists: InstanceExists,
) -> APIRouter:
    """返回挂在 /api/v1/router 前缀下的 APIRouter, 由 app 装配时 include_router."""
    router: APIRouter = APIRouter(prefix=ROUTER_PREFIX)
    register_github_ingress_routes(router, verifier, ledger, worker, instance_exists)
    return router
