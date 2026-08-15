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


def register_messaging_event_routes(router: APIRouter, settings: Settings) -> None:
    @router.post("/messaging/events/{kind}")
    def receive_event(
        kind: str,
        payload: dict[str, Any],
        messaging_token: Annotated[str | None, Header(alias=EVENT_TOKEN_HEADER)] = None,
    ) -> dict[str, object]:
        token: str = (messaging_token or "").strip()
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
