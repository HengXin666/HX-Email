"""Login ticket, QQ login probe and login status."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from hx_email.api.dependencies import require_user
from hx_email.api.impl.messaging.serializers import (
    login_state_dict,
    login_ticket_dict,
    require_instance,
)
from hx_email.config import Settings
from hx_email.server.messaging.impl.probe import probe_qq_login
from hx_email.server.messaging.types import LoginState, LoginTicket


def register_login_routes(router: APIRouter, settings: Settings) -> None:
    @router.post("/messaging/instances/{instance_id}/login")
    def login(
        instance_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        _instance, adapter = require_instance(settings, user.id, instance_id)
        ticket: LoginTicket = adapter.create_login()
        return {"success": True, "login": login_ticket_dict(ticket)}

    @router.post("/messaging/instances/{instance_id}/login/probe")
    def login_probe(
        instance_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        instance, _adapter = require_instance(settings, user.id, instance_id)
        if instance.kind != "qq":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only QQ instances support login probing",
            )
        return {"success": True, "probe": probe_qq_login(instance)}

    @router.post("/messaging/instances/{instance_id}/login/status")
    def login_status(
        instance_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        _instance, adapter = require_instance(settings, user.id, instance_id)
        state: LoginState = adapter.check_login()
        return {"success": True, "login": login_state_dict(state)}
