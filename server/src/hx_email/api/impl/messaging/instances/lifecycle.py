"""Catalog, instance CRUD, connect / disconnect and config updates."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from hx_email.api.dependencies import require_user
from hx_email.api.impl.mcp_resources.watch import announce_list_changed
from hx_email.api.impl.messaging.schemas import (
    MessagingConfigUpdate,
    MessagingInstanceCreate,
)
from hx_email.api.impl.messaging.serializers import (
    instance_detail,
    instance_dict,
    require_instance,
    safe_adapter,
    status_dict,
)
from hx_email.config import Settings
from hx_email.server.messaging.registry import catalog, creation_error, drop_adapter
from hx_email.server.messaging.store import (
    create_instance,
    delete_instance,
    get_instance,
    list_instances,
    update_instance_config,
    update_instance_status,
)
from hx_email.server.messaging.types import MessagingError, MessagingInstance


def register_lifecycle_routes(router: APIRouter, settings: Settings) -> None:
    @router.get("/messaging/catalog")
    def get_catalog(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return {"success": True, "plugins": catalog()}

    @router.get("/messaging/instances")
    def get_instances(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        instances: list[MessagingInstance] = list_instances(settings, user.id)
        return {
            "success": True,
            "instances": [instance_dict(item, safe_adapter(settings, item)) for item in instances],
        }

    @router.post("/messaging/instances", status_code=status.HTTP_201_CREATED)
    def create(
        payload: MessagingInstanceCreate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        config: dict[str, str] = dict(payload.config)
        if (reason := creation_error(payload.kind, config)) is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)
        name: str = payload.name.strip() or payload.kind
        instance: MessagingInstance = create_instance(settings, user.id, payload.kind, name, config)
        announce_list_changed(user.id)
        return {"success": True, "instance": instance_dict(instance)}

    @router.get("/messaging/instances/{instance_id}")
    def get_one(
        instance_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        instance: MessagingInstance | None = get_instance(settings, user.id, instance_id)
        if instance is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Messaging instance not found",
            )
        return {"success": True, "instance": instance_detail(settings, instance)}

    @router.delete("/messaging/instances/{instance_id}")
    def delete(
        instance_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        if not delete_instance(settings, user.id, instance_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Messaging instance not found",
            )
        drop_adapter(instance_id)
        announce_list_changed(user.id)
        return {"success": True}

    @router.post("/messaging/instances/{instance_id}/connect")
    def connect(
        instance_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        _instance, adapter = require_instance(settings, user.id, instance_id)
        try:
            adapter.start()
        except MessagingError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error
        return {"success": True, "status": status_dict(adapter.status())}

    @router.put("/messaging/instances/{instance_id}/config")
    def update_config(
        instance_id: int,
        payload: MessagingConfigUpdate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        current = get_instance(settings, user.id, instance_id)
        if current is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Messaging instance not found",
            )
        merged: dict[str, str] = {**current.config, **payload.config}
        updated = update_instance_config(settings, user.id, instance_id, merged)
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Messaging instance not found",
            )
        drop_adapter(instance_id)
        return {"success": True, "instance": instance_dict(updated)}

    @router.post("/messaging/instances/{instance_id}/disconnect")
    def disconnect(
        instance_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        instance, adapter = require_instance(settings, user.id, instance_id)
        adapter.stop()
        update_instance_status(settings, instance.id, "stopped")
        return {"success": True}
