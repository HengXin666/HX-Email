"""Plugin config (get/set/schema) route registration."""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, Header

from hx_email.api.dependencies import require_user
from hx_email.api.schemas import PluginConfigWrite
from hx_email.config import Settings
from hx_email.server.plugins import (
    get_plugin_config,
    get_plugin_config_schema,
    save_plugin_config,
)


def register_plugin_config_routes(app: FastAPI, settings: Settings) -> None:
    @app.get("/plugins/{name}/config/schema")
    def get_config_schema(
        name: str,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        return {"success": True, "schema": get_plugin_config_schema(name)}

    @app.get("/plugins/{name}/config")
    def get_config(
        name: str,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        config = get_plugin_config(settings, name)
        return {"success": True, "config": config if config is not None else {}}

    @app.post("/plugins/{name}/config")
    def save_config(
        name: str,
        payload: PluginConfigWrite,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        require_user(settings, authorization)
        save_plugin_config(settings, name, payload.config)
        return {"success": True}
