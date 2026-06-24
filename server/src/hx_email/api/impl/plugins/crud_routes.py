"""Plugin CRUD (install/uninstall/list/test) route registration."""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, status

from hx_email.api.dependencies import require_user
from hx_email.api.schemas import PluginInstallRequest
from hx_email.config import Settings
from hx_email.server.plugins import (
    install_plugin,
    list_plugins,
    test_plugin_connection,
    uninstall_plugin,
)


def register_plugin_crud_routes(app: FastAPI, settings: Settings) -> None:
    @app.get("/plugins")
    def get_plugins(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return {"success": True, "plugins": list_plugins()}

    @app.post("/plugins/install")
    def install(
        payload: PluginInstallRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        result = install_plugin(settings, source=payload.source, name=payload.name or "")
        return {"success": True, "data": result}

    @app.post("/plugins/{name}/uninstall")
    def uninstall(
        name: str,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        removed = uninstall_plugin(settings, name)
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plugin '{name}' not found",
            )
        return {"success": True}

    @app.post("/plugins/{name}/test-connection")
    def test_connection(
        name: str,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        result = test_plugin_connection(settings, name)
        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(result.get("message", "Test failed")),
            )
        return {"success": True, "data": result}
