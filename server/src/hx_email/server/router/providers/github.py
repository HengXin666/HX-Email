"""GitHub App provider: 实现路由层 MessagingProvider 协议 (ADR 0005 第 4 节).

共享契约来自 server/router/provider.py, GitHub 专有的写动作与限额在 impl/github_contract.py.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Literal

from hx_email.server.messaging.types import Capabilities
from hx_email.server.router.provider import (
    ActionCall,
    OutboundPayload,
    ProviderLimits,
    SendResult,
    SessionRef,
)
from hx_email.server.router.providers.impl.github.github_auth import (
    Clock,
    GitHubAppConfig,
    InstallationToken,
    InstallationTokenCache,
    TokenIssueError,
    utc_now,
)
from hx_email.server.router.providers.impl.github.github_contract import (
    GITHUB_LIMITS,
    GitHubWriteAction,
)
from hx_email.server.router.providers.impl.github.github_events import (
    DELIVERY_HEADER,
    EVENT_HEADER,
    SIGNATURE_HEADER,
    TARGET_ID_HEADER,
    AppIdentity,
    EventOutcome,
    JsonDict,
    lower_headers,
    map_event,
    verify_signature,
)
from hx_email.server.router.providers.impl.github.github_http import (
    GITHUB_API,
    HttpResponse,
    HttpTransport,
    RequestsTransport,
    TransportConnectError,
    TransportTimeoutError,
    classify_response,
    failed,
    github_headers,
    retryable,
)
from hx_email.server.router.providers.impl.github_reactions import (
    REACTION_PREFIX,
    ReactionRequest,
    reaction_request,
)

MARKER_TEMPLATE: str = "<!-- hx-router delivery={delivery_id} -->"
GITHUB_CAPABILITIES: Capabilities = Capabilities(
    supports_qr_login=False,
    supports_groups=True,
    supports_history=True,
    risk_level="official",
    risk_notice="使用官方 GitHub App, 无封号风险, 权限按最小集申请",
)


def build_write_action(session: SessionRef, payload: OutboundPayload) -> GitHubWriteAction | None:
    """session 地址按规格第 2 节解析: 前三个冒号拆 4 段, 第 4 段原样为 peer."""
    parts: list[str] = session.address.split(":", 3)
    if len(parts) != 4 or parts[0] != "github":
        return None
    session_type, peer = parts[2], parts[3]
    body: str = f"{payload.text}\n\n{MARKER_TEMPLATE.format(delivery_id=payload.delivery_id)}"
    if session_type == "repo":
        if "/" not in peer or not payload.title:
            return None
        return GitHubWriteAction(
            "open_issue", peer, payload.delivery_id, body=body, title=payload.title
        )
    repo, sep, number = peer.rpartition("#")
    if session_type != "issue" or not sep or "/" not in repo or not number.isdigit():
        return None
    if payload.reply_to.startswith("rc:") and payload.reply_to[3:].isdigit():
        return GitHubWriteAction(
            "reply_review_comment",
            repo,
            payload.delivery_id,
            int(number),
            body,
            reply_to_comment_id=int(payload.reply_to[3:]),
        )
    if payload.reply_to and not payload.reply_to.startswith("ic:"):
        return None
    return GitHubWriteAction("comment", repo, payload.delivery_id, int(number), body)


def action_request(action: GitHubWriteAction) -> tuple[str, JsonDict, str]:
    """返回 (url, 请求体, platform_message_id 前缀)."""
    base: str = f"{GITHUB_API}/repos/{action.repo_full_name}"
    if action.kind == "open_issue":
        return f"{base}/issues", {"title": action.title, "body": action.body}, "is"
    if action.kind == "reply_review_comment":
        url: str = f"{base}/pulls/{action.number}/comments/{action.reply_to_comment_id}/replies"
        return url, {"body": action.body}, "rc"
    return f"{base}/issues/{action.number}/comments", {"body": action.body}, "ic"


class GitHubAppProvider:
    """一个 provider 服务全部 GitHub 实例; config_loader 按 instance_id 读出解密后的配置."""

    platform: str = "github"
    delivery_mode: Literal["push", "pull"] = "push"
    limits: ProviderLimits = GITHUB_LIMITS

    def __init__(
        self,
        config_loader: Callable[[int], GitHubAppConfig],
        transport: HttpTransport | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self.config_loader: Callable[[int], GitHubAppConfig] = config_loader
        self.transport: HttpTransport = transport or RequestsTransport()
        self.clock: Clock = clock
        self.caches: dict[int, InstallationTokenCache] = {}

    def cache(self, instance_id: int) -> InstallationTokenCache:
        if instance_id not in self.caches:
            config: GitHubAppConfig = self.config_loader(instance_id)
            self.caches[instance_id] = InstallationTokenCache(config, self.transport, self.clock)
        return self.caches[instance_id]

    def list_sessions(self, instance_id: int) -> list[SessionRef]:
        # 会话列表取自路由层 store 已入库的线程 (规格 8.3), 由 R1 的 facade 提供
        return []

    def verify_event(self, instance_id: int, headers: dict[str, str], body: bytes) -> bool:
        lowered: dict[str, str] = lower_headers(headers)
        config: GitHubAppConfig = self.config_loader(instance_id)
        target: str = lowered.get(TARGET_ID_HEADER, "")
        if target and config.app_id and target != config.app_id:
            return False
        return verify_signature(config.webhook_secrets(), body, lowered.get(SIGNATURE_HEADER))

    def parse_event(
        self, instance_id: int, headers: dict[str, str], body: bytes
    ) -> list[dict[str, object]]:
        lowered: dict[str, str] = lower_headers(headers)
        payload: object = json.loads(body)
        if not isinstance(payload, dict):
            return []
        cache: InstallationTokenCache = self.cache(instance_id)
        identity: AppIdentity = AppIdentity(cache.config.app_id, cache.config.app_slug)
        outcome: EventOutcome = map_event(
            instance_id,
            lowered.get(EVENT_HEADER, ""),
            lowered.get(DELIVERY_HEADER, ""),
            payload,
            identity,
        )
        if outcome.installation_id is not None:
            if outcome.installation_removed:
                cache.forget_installation(outcome.installation_id)
            cache.remember_repos(outcome.installation_id, outcome.repos_added)
        cache.forget_repos(outcome.repos_removed)
        return list(outcome.envelopes)

    def installation_token(
        self, instance_id: int, installation_id: int, *, force_refresh: bool = False
    ) -> InstallationToken:
        return self.cache(instance_id).get(installation_id, force_refresh=force_refresh)

    def call(
        self, instance_id: int, repo: str, method: str, url: str, body: JsonDict | None
    ) -> HttpResponse:
        """带 installation token 调 REST; 401 时强制刷新 token 重试 1 次."""
        cache: InstallationTokenCache = self.cache(instance_id)
        installation_id: int | None = cache.installation_for_repo(repo)
        if installation_id is None:
            return HttpResponse(404, {}, {"message": f"App is not installed on {repo}"})
        token: InstallationToken = cache.get(installation_id)
        response: HttpResponse = self.transport.request(
            method, url, github_headers(token.token), body
        )
        if response.status == 401:
            token = cache.get(installation_id, force_refresh=True)
            response = self.transport.request(method, url, github_headers(token.token), body)
        return response

    def send(self, session: SessionRef, payload: OutboundPayload) -> SendResult:
        action: GitHubWriteAction | None = build_write_action(session, payload)
        if action is None:
            return failed("session_not_sendable", f"cannot send to {session.address}")
        url, request_body, prefix = action_request(action)
        return self.post(session.instance_id, action.repo_full_name, url, request_body, prefix)

    # comment_create 复用 send 的评论路径与隐藏标记; reaction_add 天然幂等, 超时直接重试不进 unknown
    # 决策记录: .agents/notes/implemented/feature/2026-11-09-github-outbound-actions.md
    def invoke(self, session: SessionRef, call: ActionCall) -> SendResult:
        if call.action == "comment_create":
            payload = OutboundPayload(
                call.delivery_id, call.params.get("text", ""), call.params.get("reply_to", ""), ""
            )
            return self.send(session, payload)
        if call.action == "reaction_add":
            request: ReactionRequest | None = reaction_request(session.address, call.params)
            if request is None:
                return failed("invalid_payload", f"cannot react on {session.address}")
            return self.post(
                session.instance_id,
                request.repo_full_name,
                request.url,
                request.body,
                REACTION_PREFIX,
                idempotent=True,
            )
        return failed("action_not_supported", f"github has no action {call.action}")

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
        except TokenIssueError as error:
            if error.status >= 500:
                return retryable("provider_error", str(error))
            return failed("token_invalid", str(error))
        return classify_response(response, int(self.clock().timestamp()), prefix)

    def reconcile_unknown(self, session: SessionRef, delivery_id: str) -> SendResult:
        """按隐藏标记查重: 找到回填 sent, 确认没有则 retry 重发一次, 查找失败保持 unknown."""
        probe: GitHubWriteAction | None = build_write_action(
            session, OutboundPayload(delivery_id, "", "", session.title or "probe")
        )
        if probe is None:
            return failed("session_not_sendable", f"cannot reconcile {session.address}")
        marker: str = MARKER_TEMPLATE.format(delivery_id=delivery_id)
        base: str = f"{GITHUB_API}/repos/{probe.repo_full_name}"
        if probe.kind == "open_issue":
            bot: str = self.cache(session.instance_id).config.bot_login
            lookups: list[tuple[str, str]] = [
                (f"{base}/issues?creator={bot}&state=all&per_page=100", "is")
            ]
        else:
            lookups = [
                (f"{base}/issues/{probe.number}/comments?per_page=100", "ic"),
                (f"{base}/pulls/{probe.number}/comments?per_page=100", "rc"),
            ]
        for url, prefix in lookups:
            try:
                response: HttpResponse = self.call(
                    session.instance_id, probe.repo_full_name, "GET", url, None
                )
            except (TransportTimeoutError, TransportConnectError, TokenIssueError) as error:
                return SendResult(
                    status="unknown", error_code="delivery_unknown", error_message=str(error)
                )
            if response.status == 404 and prefix == "rc":
                continue
            if response.status != 200 or not isinstance(response.body, list):
                return SendResult(
                    status="unknown",
                    error_code="delivery_unknown",
                    error_message=f"lookup failed ({response.status})",
                )
            for item in response.body:
                if isinstance(item, dict) and marker in str(item.get("body") or ""):
                    return SendResult(status="sent", platform_message_id=f"{prefix}:{item['id']}")
        return SendResult(
            status="retry",
            retryable=True,
            error_code="marker_not_found",
            error_message="no comment carries this delivery marker",
        )
