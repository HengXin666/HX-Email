"""GitHub App Manifest 一键创建: manifest 内容, 一次性 state, code 兑换与凭据落库.

流程:
1. 管理员发起, 服务端建 state 存库 (10 分钟, 绑定一个 github 实例), 前端整页表单 POST manifest
2. GitHub 建好 App 后带 code 与 state 跳回回调
3. 回调先确认加密密钥可用, 再一次性消费 state, 最后才花掉 code (1 小时有效, 只能用一次)
4. 兑换结果经 github_auth.seal_app_config 加密写入该实例的 config_encrypted

webhook 地址带 instance_id, 因为入站端点按实例区分 (/api/v1/router/ingress/github/{id}),
manifest 一旦提交 GitHub 就写死了, 所以实例必须在生成 manifest 之前就存在.
"""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Final

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.security import decrypt_secret, encrypt_secret
from hx_email.server.router.providers.impl.github.github_auth import (
    GitHubAppConfig,
    seal_app_config,
)
from hx_email.server.router.providers.impl.github.github_http import (
    GITHUB_API,
    HttpResponse,
    HttpTransport,
)

STATE_TTL: Final[timedelta] = timedelta(minutes=10)
TIME_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"
INGRESS_PATH: Final[str] = "/api/v1/router/ingress/github/{instance_id}"
CALLBACK_PATH: Final[str] = "/api/v1/router/github/callback"
NAME_PREFIX: Final[str] = "hx-email-"
CODE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
# 权限最小集: contents 只读, 仅为收 push 与 commit_comment; discussions 要写, 供 discussion_create
# 与 discussion_comment_create; 已安装的 App 扩权后要所有者在 GitHub 上重新同意
DEFAULT_PERMISSIONS: Final[dict[str, str]] = {
    "metadata": "read",
    "issues": "write",
    "pull_requests": "write",
    "contents": "read",
    "discussions": "write",
}
# installation 与 installation_repositories 默认投递, 写进来 GitHub 会拒掉整个 manifest
DEFAULT_EVENTS: Final[tuple[str, ...]] = (
    "issue_comment",
    "issues",
    "pull_request",
    "pull_request_review",
    "pull_request_review_comment",
    "discussion",
    "discussion_comment",
    "commit_comment",
    "push",
)
REQUIRED_FIELDS: Final[tuple[str, ...]] = ("id", "slug", "client_id", "pem", "webhook_secret")


class ManifestError(Exception):
    """流程失败; reason 是给前端 error= 参数用的短码."""

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason: str = reason


def utc_now() -> datetime:
    return datetime.now(UTC)


def create_state() -> str:
    return secrets.token_urlsafe(32)


def create_name_suffix() -> str:
    """6 位 hex; App 名在 GitHub 全局唯一, 后缀避免撞名."""
    return secrets.token_hex(3)


# GitHub App 一键创建与秘密字段只写不读的决策
# 决策记录: .agents/notes/implemented/feature/2026-11-03-github-app-manifest-flow.md
def build_manifest(base_url: str, name_suffix: str, instance_id: int) -> dict[str, object]:
    root: str = base_url.rstrip("/")
    return {
        "name": f"{NAME_PREFIX}{name_suffix}",
        "url": root,
        "hook_attributes": {
            "url": root + INGRESS_PATH.format(instance_id=instance_id),
            "active": True,
        },
        "redirect_url": root + CALLBACK_PATH,
        "public": False,
        "default_permissions": dict(DEFAULT_PERMISSIONS),
        "default_events": list(DEFAULT_EVENTS),
    }


def save_state(settings: Settings, state: str, instance_id: int, now: datetime) -> datetime:
    """存一条新 state, 顺手清掉过期行; 返回过期时间."""
    cutoff: str = (now - STATE_TTL).strftime(TIME_FORMAT)
    with connect(settings) as connection:
        connection.execute("DELETE FROM router_github_app_states WHERE created_at <= ?", (cutoff,))
        connection.execute(
            "INSERT INTO router_github_app_states (state, created_at, used, instance_id) "
            "VALUES (?, ?, 0, ?)",
            (state, now.strftime(TIME_FORMAT), instance_id),
        )
    return now + STATE_TTL


def consume_state(settings: Settings, state: str, now: datetime) -> int:
    """原子消费: 只有 used = 0 且未过期的行能被一个回调改成 1, 返回绑定的 instance_id."""
    cutoff: str = (now - STATE_TTL).strftime(TIME_FORMAT)
    with connect(settings) as connection:
        cursor = connection.execute(
            "UPDATE router_github_app_states SET used = 1 "
            "WHERE state = ? AND used = 0 AND created_at > ?",
            (state, cutoff),
        )
        if cursor.rowcount != 1:
            raise ManifestError("invalid_state", "state 无效, 已使用或已过期")
        row = connection.execute(
            "SELECT instance_id FROM router_github_app_states WHERE state = ?", (state,)
        ).fetchone()
    return int(row["instance_id"])


def ensure_encryption_ready(settings: Settings) -> None:
    """花掉 code 之前确认密钥能加解密, 否则 App 建出来私钥却无处可存."""
    probe: str = secrets.token_hex(8)
    try:
        ready: bool = decrypt_secret(settings, encrypt_secret(settings, probe)) == probe
    except Exception as error:
        raise ManifestError("encryption_unavailable", str(error)) from error
    if not ready:
        raise ManifestError("encryption_unavailable", "加密密钥自检失败")


def convert_manifest(code: str, http: HttpTransport) -> dict[str, object]:
    """POST /app-manifests/{code}/conversions, 无需鉴权; 返回体含 pem 等明文, 调用方立刻加密."""
    if not CODE_PATTERN.match(code):
        raise ManifestError("invalid_code", "code 格式不对")
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "hx-email-router",
    }
    url: str = f"{GITHUB_API}/app-manifests/{code}/conversions"
    response: HttpResponse = http.request("POST", url, headers, None)
    body: dict[str, object] = response.as_dict()
    if response.status != 201:
        raise ManifestError("conversion_failed", f"GitHub 返回 {response.status}")
    missing: list[str] = [key for key in REQUIRED_FIELDS if not body.get(key)]
    if missing:
        raise ManifestError("conversion_incomplete", f"缺少字段: {', '.join(missing)}")
    return body


def config_from_conversion(body: dict[str, object]) -> GitHubAppConfig:
    """只取六个配置键需要的字段; client_secret 不落库, 本方案不启用 user-to-server 授权."""
    return GitHubAppConfig(
        app_id=str(body["id"]),
        client_id=str(body["client_id"]),
        app_slug=str(body["slug"]),
        private_key_pem=str(body["pem"]),
        webhook_secret=str(body["webhook_secret"]),
    )


def store_app_config(settings: Settings, instance_id: int, config: GitHubAppConfig) -> None:
    sealed: str = seal_app_config(settings, config)
    with connect(settings) as connection:
        connection.execute(
            "UPDATE messaging_instances SET config_encrypted = ?, updated_at = datetime('now') "
            "WHERE id = ? AND kind = 'github'",
            (sealed, instance_id),
        )


def public_app_summary(config: GitHubAppConfig) -> dict[str, object]:
    """管理接口的唯一出口: 秘密字段只给布尔."""
    return {
        "app_id": config.app_id,
        "app_slug": config.app_slug,
        "client_id": config.client_id,
        "has_private_key": bool(config.private_key_pem),
        "has_webhook_secret": bool(config.webhook_secret),
    }
