"""GitHub 用户账号 (gh CLI) 的接入端点: 保存 CLI 路径与仓库并检查, 或对已有实例重新检查.

只有管理员可用: CLI 路径是服务端要执行的程序, 不能让普通用户指定. 通用建实例接口不接受
``github_user`` (``registry.creation_error``), 实例只能从这里建. 请求体里没有任何 token 字段.
"""

from __future__ import annotations

from typing import Annotated, Final

from fastapi import APIRouter, Body, Header, HTTPException, status

from hx_email.api.dependencies import require_admin
from hx_email.api.impl.messaging.serializers import instance_dict
from hx_email.config import Settings
from hx_email.server.contract.github_user.config import (
    CLI_KEY,
    LOGIN_KEY,
    REPOSITORY_KEY,
    config_problem,
)
from hx_email.server.messaging.store import (
    create_instance,
    get_instance,
    update_instance_config,
    update_instance_status,
)
from hx_email.server.messaging.types import MessagingInstance
from hx_email.server.router.providers.impl.github_user.gh_setup import SetupReport, check_setup

PREFIX: Final[str] = "/router/github_user"
KIND: Final[str] = "github_user"


async def run_check(
    settings: Settings, user_id: int, instance: MessagingInstance
) -> dict[str, object]:
    report: SetupReport = await check_setup(instance.config)
    config: dict[str, str] = {**instance.config, LOGIN_KEY: report.login if report.ok else ""}
    saved: MessagingInstance | None = update_instance_config(settings, user_id, instance.id, config)
    update_instance_status(settings, instance.id, "online" if report.ok else "error")
    fresh: MessagingInstance | None = get_instance(settings, user_id, instance.id) or saved
    return {"report": report.to_dict(), "instance": instance_dict(fresh) if fresh else {}}


def owned(settings: Settings, user_id: int, instance_id: int) -> MessagingInstance:
    instance: MessagingInstance | None = get_instance(settings, user_id, instance_id)
    if instance is None or instance.kind != KIND:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "GitHub account instance not found")
    return instance


# 仅管理员; 保存即检查, 检查通过才置 online, 轮询与出站只认 online 实例
# 决策记录: .agents/notes/implemented/feature/2026-11-09-github-cli-account.md
def register_github_user_routes(router: APIRouter, settings: Settings) -> None:
    @router.post(f"{PREFIX}/save")
    async def save_account(
        cli: Annotated[str, Body(max_length=4096)],
        repository: Annotated[str, Body(max_length=200)],
        instance_id: Annotated[int, Body()] = 0,
        name: Annotated[str, Body(max_length=100)] = "",
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_admin(settings, authorization)
        fields: dict[str, str] = {CLI_KEY: cli.strip(), REPOSITORY_KEY: repository.strip()}
        if (problem := config_problem(fields)) is not None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
        if instance_id:
            current: MessagingInstance = owned(settings, user.id, instance_id)
            merged: dict[str, str] = {**current.config, **fields}
            instance = update_instance_config(settings, user.id, instance_id, merged) or current
        else:
            title: str = name.strip() or f"GitHub 账号 ({fields[REPOSITORY_KEY]})"
            instance = create_instance(settings, user.id, KIND, title, fields)
        return await run_check(settings, user.id, instance)

    @router.post(f"{PREFIX}/check")
    async def check_account(
        instance_id: Annotated[int, Body(embed=True)],
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_admin(settings, authorization)
        return await run_check(settings, user.id, owned(settings, user.id, instance_id))
