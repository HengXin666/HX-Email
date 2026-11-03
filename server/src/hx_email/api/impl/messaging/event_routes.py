"""Event callback route: OneBot/NapCat pushes messages to HX-Email."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, status

from hx_email.config import Settings
from hx_email.server.messaging.impl.events import ingest_event
from hx_email.server.messaging.store import (
    find_instance_by_event_token,
    save_message,
    update_instance_status,
)
from hx_email.server.messaging.types import MessagingInstance, MessagingMessage

EVENT_TOKEN_HEADER: str = "X-Messaging-Token"
BEARER_PREFIX: str = "Bearer "


# OneBot httpClients 只发 Authorization 头, receive_event 因此同时接受它与 X-Messaging-Token
# 决策记录: .agents/notes/implemented/feature/2026-11-03-qq-live-wiring-fixes.md
def register_messaging_event_routes(router: APIRouter, settings: Settings) -> None:
    @router.post("/messaging/events/{kind}")
    def receive_event(
        kind: str,
        payload: dict[str, Any],
        messaging_token: Annotated[str | None, Header(alias=EVENT_TOKEN_HEADER)] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        # OneBot 的 httpClients 只会发 Authorization 头, 它没有自定义头的写法;
        # 所以这里两种都接受, 取到哪个用哪个.
        token: str = (messaging_token or "").strip()
        if not token:
            raw: str = (authorization or "").strip()
            token = raw[len(BEARER_PREFIX) :].strip() if raw.startswith(BEARER_PREFIX) else raw
        instance: MessagingInstance | None = find_instance_by_event_token(settings, kind, token)
        if instance is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid messaging event token",
            )
        message: MessagingMessage | None = ingest_event(payload)
        if message is not None:
            save_message(settings, instance.id, message)
        update_instance_status(settings, instance.id, "online")
        return {"success": True, "stored": message is not None}
