"""REST routes: catalog, instance lifecycle, connection and login.

The handlers live in ``instances/`` (lifecycle, login, embedded engine); this module only
registers them in the original order so the route table does not change.
"""

from __future__ import annotations

from fastapi import APIRouter

from hx_email.api.impl.messaging.instances.engine import register_engine_routes
from hx_email.api.impl.messaging.instances.lifecycle import register_lifecycle_routes
from hx_email.api.impl.messaging.instances.login import register_login_routes
from hx_email.config import Settings


# 原 routes.py 顶到 300 行上限, 按生命周期 / 登录 / 内置引擎拆分, 注册顺序与路径不变
# 决策记录: .agents/notes/implemented/feature/2026-11-10-messaging-routes-split.md
def register_messaging_routes(router: APIRouter, settings: Settings) -> None:
    register_lifecycle_routes(router, settings)
    register_login_routes(router, settings)
    register_engine_routes(router, settings)
