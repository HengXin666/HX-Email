"""GitHub 用户账号 provider: 以真人或专用账号身份, 经 gh CLI 收发 (ADR 0010).

与 ``GitHubAppProvider`` 是两个平台, 互不改动: App 以 bot 身份由仓库级 webhook 推送, 这里以
账号身份轮询 notifications. 出站复用 App 的全部写逻辑 (``build_write_action``, ``action_request``,
``invoke_github``, GraphQL 分类与隐藏标记), 只把网络出口换成 ``<cli> api``, 把地址前缀
``github_user`` 换成 App 写代码认识的 ``github``. 幂等, unknown 与重试分类因此与 App 完全一致.

一个实例只服务配置的那一个仓库: 对别的仓库的写一律拒绝, 不调用 CLI.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Literal

from hx_email.server.contract.github_user.config import GhUserConfig
from hx_email.server.router.provider import (
    ActionCall,
    OutboundPayload,
    ProviderLimits,
    SendResult,
    SessionRef,
)
from hx_email.server.router.providers.github import action_request, build_write_action
from hx_email.server.router.providers.impl.github.github_auth import Clock, utc_now
from hx_email.server.router.providers.impl.github.github_contract import (
    GITHUB_LIMITS,
    GitHubWriteAction,
)
from hx_email.server.router.providers.impl.github.github_events import JsonDict
from hx_email.server.router.providers.impl.github.github_http import (
    HttpResponse,
    TransportConnectError,
    TransportTimeoutError,
    classify_response,
    failed,
    retryable,
)
from hx_email.server.router.providers.impl.github_user.gh_cli import (
    DEFAULT_TIMEOUT_SECONDS,
    GhCli,
    run_sync,
)
from hx_email.server.router.providers.impl.github_user.gh_mapping import PLATFORM, app_address
from hx_email.server.router.providers.impl.github_write.actions import invoke_github

ConfigLoader = Callable[[int], GhUserConfig]


def app_session(session: SessionRef) -> SessionRef:
    return replace(session, address=app_address(session.address), platform="github")


class GitHubUserProvider:
    """One provider per instance; the config is read on every call, never cached."""

    platform: str = PLATFORM
    delivery_mode: Literal["push", "pull"] = "pull"
    limits: ProviderLimits = GITHUB_LIMITS

    def __init__(
        self,
        config_loader: ConfigLoader,
        clock: Clock = utc_now,
        env: Mapping[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.config_loader: ConfigLoader = config_loader
        self.clock: Clock = clock
        self.env: Mapping[str, str] | None = env
        self.timeout: float = timeout

    def list_sessions(self, instance_id: int) -> list[SessionRef]:
        return []  # 会话取自已入库的线程, 与 App 相同

    def verify_event(self, instance_id: int, headers: dict[str, str], body: bytes) -> bool:
        return False  # 轮询平台没有推送入口

    def parse_event(
        self, instance_id: int, headers: dict[str, str], body: bytes
    ) -> list[dict[str, object]]:
        return []

    # 网络出口换成 <cli> api, 其余照搬 App; 只写配置的那个仓库, 未通过检查的实例不调用 CLI
    # 决策记录: .agents/notes/implemented/feature/2026-11-09-github-cli-account.md
    def call(
        self, instance_id: int, repo: str, method: str, url: str, body: JsonDict | None
    ) -> HttpResponse:
        config: GhUserConfig = self.config_loader(instance_id)
        if not config.ready:
            raise TransportConnectError("GitHub account is not checked; run the setup check")
        if repo.lower() != config.repository.lower():
            message: str = f"{repo} is not the repository configured on this account"
            return HttpResponse(404, {}, {"message": message})
        cli: GhCli = GhCli(config.cli, self.timeout, self.env)
        return run_sync(cli.api(method, url, body))

    def send(self, session: SessionRef, payload: OutboundPayload) -> SendResult:
        action: GitHubWriteAction | None = build_write_action(app_session(session), payload)
        if action is None:
            return failed("session_not_sendable", f"cannot send to {session.address}")
        url, request_body, prefix = action_request(action)
        return self.post(session.instance_id, action.repo_full_name, url, request_body, prefix)

    def invoke(self, session: SessionRef, call: ActionCall) -> SendResult:
        return invoke_github(self, app_session(session), call)

    def post(
        self,
        instance_id: int,
        repo: str,
        url: str,
        body: JsonDict,
        prefix: str,
        *,
        idempotent: bool = False,
    ) -> SendResult:
        try:
            response: HttpResponse = self.call(instance_id, repo, "POST", url, body)
        except TransportTimeoutError as error:
            if idempotent:
                return retryable("provider_timeout", str(error))
            return SendResult(
                status="unknown", error_code="delivery_unknown", error_message=str(error)
            )
        except TransportConnectError as error:
            return retryable("provider_offline", str(error))
        return classify_response(response, int(self.clock().timestamp()), prefix)
