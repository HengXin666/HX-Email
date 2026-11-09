"""Setup 检查: CLI 能否运行, 能否读到账号, 对所配置仓库是否有读与推送权限.

每一步失败都给一个稳定的错误码和一句可照做的提示, 前端照码显示. 检查只读不写, 通过时
返回登录名, 由调用方写回实例配置. token 从不出现在这里: 能读到 ``/user`` 就说明包装脚本
自己的 ``GH_CONFIG_DIR`` 里有凭据.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from hx_email.server.contract.github_user.actions import NOTIFICATION_SCOPES
from hx_email.server.contract.github_user.config import (
    CLI_KEY,
    REPOSITORY_KEY,
    REPOSITORY_PATTERN,
)
from hx_email.server.router.providers.impl.github.github_http import (
    HttpResponse,
    TransportConnectError,
    TransportTimeoutError,
)
from hx_email.server.router.providers.impl.github_user.gh_cli import (
    DEFAULT_TIMEOUT_SECONDS,
    CliTimeoutError,
    GhCli,
)

HINTS: Final[dict[str, str]] = {
    "cli_not_configured": "填写 gh 包装脚本的绝对路径, 例如 /home/you/.local/bin/gh-agent",
    "cli_not_absolute": "CLI 路径必须是绝对路径, 服务端不按 PATH 查找",
    "cli_not_found": "服务端找不到这个文件; 确认脚本在运行本服务的机器上",
    "cli_not_executable": "给脚本加上可执行权限: chmod +x <路径>",
    "cli_timeout": "CLI 在限定时间内没有返回; 检查网络或代理",
    "cli_failed": "CLI 运行失败; 在终端里手动执行同一条命令看报错",
    "not_authenticated": "在终端运行 <cli> auth login 登录这个账号",
    "repository_invalid": "仓库写成 owner/name",
    "repo_not_visible": "这个账号看不到该仓库; 确认仓库名, 或把账号加为协作者",
    "repo_no_read": "这个账号对仓库没有读权限",
    "repo_no_push": "这个账号对仓库没有推送 (写) 权限; 回帖, review 与 discussion 都需要",
}


@dataclass(frozen=True)
class SetupReport:
    ok: bool
    code: str
    message: str
    login: str = ""
    scopes: tuple[str, ...] = ()
    missing_scopes: tuple[str, ...] = ()
    hint: str = field(default="")

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "code": self.code,
            "message": self.message,
            "hint": self.hint or HINTS.get(self.code, ""),
            "login": self.login,
            "scopes": list(self.scopes),
            "missing_scopes": list(self.missing_scopes),
        }


def failure(code: str, message: str, login: str = "", hint: str = "") -> SetupReport:
    return SetupReport(False, code, message, login, hint=hint)


def path_problem(cli: str) -> SetupReport | None:
    if not cli:
        return failure("cli_not_configured", "没有配置 CLI 路径")
    path: Path = Path(cli)
    if not path.is_absolute():
        return failure("cli_not_absolute", f"{cli} 不是绝对路径")
    if not path.is_file():
        return failure("cli_not_found", f"{cli} 不存在")
    if not os.access(path, os.X_OK):
        return failure("cli_not_executable", f"{cli} 没有可执行权限")
    return None


def missing(scopes: tuple[str, ...]) -> tuple[str, ...]:
    """Classic tokens list their scopes; fine-grained ones send no header, so nothing is missing."""
    if not scopes:
        return ()
    needed: list[str] = [] if "repo" in scopes else ["repo"]
    if not any(scope in scopes for scope in NOTIFICATION_SCOPES):
        needed.append("notifications")
    return tuple(needed)


# 每步失败给稳定错误码与提示; 只读检查, 通过时返回登录名由调用方写回配置
async def check_setup(
    raw: Mapping[str, str],
    env: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> SetupReport:
    cli: str = str(raw.get(CLI_KEY, "")).strip()
    repo: str = str(raw.get(REPOSITORY_KEY, "")).strip()
    problem: SetupReport | None = path_problem(cli)
    if problem is not None:
        return problem
    if REPOSITORY_PATTERN.match(repo) is None:
        return failure("repository_invalid", f"{repo or '(空)'} 不是 owner/name")
    gh: GhCli = GhCli(cli, timeout, env)
    try:
        user: HttpResponse = await gh.api("GET", "user")
        login: str = str(user.as_dict().get("login") or "")
        if user.status == 401:
            hint: str = f"在终端运行 {cli} auth login 登录这个账号"
            return failure("not_authenticated", f"{cli} 没有登录 GitHub", hint=hint)
        if user.status != 200 or not login:
            return failure("cli_failed", f"{cli} api user 返回 HTTP {user.status}")
        found: HttpResponse = await gh.api("GET", f"repos/{repo}")
    except CliTimeoutError as error:
        return failure("cli_timeout", str(error))
    except (TransportConnectError, TransportTimeoutError) as error:
        return failure("cli_failed", str(error))
    if found.status in (403, 404):
        return failure("repo_not_visible", f"{login} 看不到 {repo} (HTTP {found.status})", login)
    if found.status != 200:
        return failure("cli_failed", f"读取 {repo} 返回 HTTP {found.status}", login)
    permissions: object = found.as_dict().get("permissions")
    granted: dict[str, object] = permissions if isinstance(permissions, dict) else {}
    if not granted.get("pull"):
        return failure("repo_no_read", f"{login} 对 {repo} 没有读权限", login)
    if not granted.get("push"):
        return failure("repo_no_push", f"{login} 对 {repo} 没有推送权限", login)
    raw_scopes: str = user.headers.get("x-oauth-scopes", "")
    scopes: tuple[str, ...] = tuple(s.strip() for s in raw_scopes.split(",") if s.strip())
    return SetupReport(True, "ok", f"已读到账号 {login}", login, scopes, missing(scopes))
