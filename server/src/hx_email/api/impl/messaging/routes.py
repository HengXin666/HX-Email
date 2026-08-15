"""REST routes: catalog, instance lifecycle, connection and login."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import Response

from hx_email.api.dependencies import require_user
from hx_email.api.impl.messaging.schemas import (
    MessagingConfigUpdate,
    MessagingInstanceCreate,
)
from hx_email.api.impl.messaging.serializers import (
    instance_dict,
    login_state_dict,
    login_ticket_dict,
    require_instance,
    safe_adapter,
    status_dict,
)
from hx_email.config import Settings
from hx_email.server.messaging.engine import (
    QQEngineManager,
    pick_free_port,
)
from hx_email.server.messaging.impl.probe import probe_qq_login
from hx_email.server.messaging.registry import catalog, drop_adapter, get_kind
from hx_email.server.messaging.store import (
    create_instance,
    delete_instance,
    get_instance,
    list_instances,
    update_instance_config,
    update_instance_status,
)
from hx_email.server.messaging.types import (
    LoginState,
    LoginTicket,
    MessagingError,
    MessagingInstance,
)


def register_messaging_routes(router: APIRouter, settings: Settings) -> None:
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
        if get_kind(payload.kind) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown messaging kind: {payload.kind}",
            )
        name: str = payload.name.strip() or payload.kind
        config: dict[str, str] = dict(payload.config)
        instance: MessagingInstance = create_instance(settings, user.id, payload.kind, name, config)
        return {"success": True, "instance": instance_dict(instance)}

    @router.get("/messaging/instances/{instance_id}")
    def get_one(
        instance_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        instance, adapter = require_instance(settings, user.id, instance_id)
        return {"success": True, "instance": instance_dict(instance, adapter)}

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

    @router.post("/messaging/instances/{instance_id}/engine/start")
    def engine_start(
        instance_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        instance, _adapter = require_instance(settings, user.id, instance_id)
        if instance.kind != "qq":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only QQ instances support the embedded engine",
            )
        config: dict[str, str] = instance.config
        api_port: int = port_from_config(config, "engine_api_port")
        webui_port: int = port_from_config(config, "engine_webui_port")
        while webui_port == api_port:
            webui_port = pick_free_port()
        event_url: str = config.get("event_callback_url", "") or (
            "http://127.0.0.1:8000/api/v1/messaging/events/qq"
        )
        token: str = config.get("event_token", "")
        manager: QQEngineManager = QQEngineManager(settings, instance.id)
        try:
            pid: int = manager.start(
                api_port,
                webui_port,
                event_url,
                token,
                proxy_url=config.get("proxy_url", ""),
            )
        except RuntimeError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(error),
            ) from error
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"启动内置引擎失败: {error}",
            ) from error
        merged: dict[str, str] = {
            **config,
            "engine_api_port": str(api_port),
            "engine_webui_port": str(webui_port),
            "api_base_url": f"http://127.0.0.1:{api_port}",
            "webui_url": f"http://127.0.0.1:{webui_port}",
        }
        updated = update_instance_config(settings, user.id, instance.id, merged)
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Messaging instance not found",
            )
        drop_adapter(instance.id)
        return {"success": True, "pid": pid, "instance": instance_dict(updated)}

    @router.post("/messaging/instances/{instance_id}/engine/stop")
    def engine_stop(
        instance_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        instance, _adapter = require_instance(settings, user.id, instance_id)
        QQEngineManager(settings, instance.id).stop()
        update_instance_status(settings, instance.id, "stopped")
        drop_adapter(instance.id)
        return {"success": True}

    @router.get("/messaging/instances/{instance_id}/login/qr")
    def login_qr(
        instance_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> Response:
        user = require_user(settings, authorization)
        instance, _adapter = require_instance(settings, user.id, instance_id)
        webui_port: int = port_from_config(instance.config, "engine_webui_port")
        image: bytes | None = QQEngineManager(settings, instance.id).qr_image(webui_port)
        if image is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="二维码暂不可用, 请先启动内置引擎",
            )
        return Response(content=image, media_type="image/png")


def port_from_config(config: dict[str, str], key: str) -> int:
    """Read a port from instance config or allocate a free one."""
    raw: str = config.get(key, "")
    if raw.isdigit():
        return int(raw)
    return pick_free_port()
