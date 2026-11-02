"""GitHub App 身份层: 配置加密存取, RS256 JWT 签发, installation token 缓存.

规格见 docs/providers/github-app.md 第 6 节与第 8.5 节.
"""

from __future__ import annotations

import json
import threading
from base64 import urlsafe_b64encode
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from hx_email.config import Settings
from hx_email.security import decrypt_secret, encrypt_secret
from hx_email.server.router.providers.impl.github.github_http import (
    GITHUB_API,
    HttpResponse,
    HttpTransport,
    github_headers,
)

JWT_BACKDATE_SECONDS: int = 60
JWT_LIFETIME_SECONDS: int = 540
TOKEN_REFRESH_MARGIN: timedelta = timedelta(minutes=5)
CONFIG_KEYS: tuple[str, ...] = (
    "app_id",
    "client_id",
    "app_slug",
    "private_key_pem",
    "webhook_secret",
    "webhook_secret_previous",
)
SECRET_CONFIG_KEYS: frozenset[str] = frozenset(
    {"private_key_pem", "webhook_secret", "webhook_secret_previous"}
)
REDACTED: str = "***"

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class GitHubAppConfig:
    app_id: str
    client_id: str
    app_slug: str
    private_key_pem: str
    webhook_secret: str
    webhook_secret_previous: str = ""

    @property
    def bot_login(self) -> str:
        return f"{self.app_slug}[bot]"

    def webhook_secrets(self) -> tuple[bytes, ...]:
        values: tuple[str, ...] = (self.webhook_secret, self.webhook_secret_previous)
        return tuple(value.encode("utf-8") for value in values if value)

    def jwt_issuer(self) -> str:
        return self.client_id or self.app_id


def seal_app_config(settings: Settings, config: GitHubAppConfig) -> str:
    """整体序列化后经 security.encrypt_secret 加密, 写入 config_encrypted 列."""
    plain: dict[str, str] = {key: str(getattr(config, key)) for key in CONFIG_KEYS}
    return encrypt_secret(settings, json.dumps(plain, ensure_ascii=False))


def open_app_config(settings: Settings, sealed: str) -> GitHubAppConfig:
    loaded: object = json.loads(decrypt_secret(settings, sealed))
    if not isinstance(loaded, dict):
        raise ValueError("GitHub App config must be a JSON object")
    values: dict[str, str] = {key: str(loaded.get(key, "") or "") for key in CONFIG_KEYS}
    return GitHubAppConfig(**values)


def redact_app_config(config: GitHubAppConfig) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in CONFIG_KEYS:
        value: str = str(getattr(config, key))
        out[key] = REDACTED if key in SECRET_CONFIG_KEYS and value else value
    return out


def b64url(raw: bytes) -> str:
    return urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def build_app_jwt(private_key_pem: str, issuer: str, now: datetime) -> str:
    """RS256 JWT: iat 回拨 60 秒抵消时钟偏差, exp 为 9 分钟后 (GitHub 上限 10 分钟)."""
    key: object = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("GitHub App private key must be an RSA key")
    issued_at: int = int(now.timestamp())
    header: dict[str, str] = {"alg": "RS256", "typ": "JWT"}
    claims: dict[str, object] = {
        "iat": issued_at - JWT_BACKDATE_SECONDS,
        "exp": issued_at + JWT_LIFETIME_SECONDS,
        "iss": issuer,
    }
    segments: list[str] = [
        b64url(json.dumps(header, separators=(",", ":")).encode()),
        b64url(json.dumps(claims, separators=(",", ":")).encode()),
    ]
    signing_input: bytes = ".".join(segments).encode("ascii")
    signature: bytes = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{segments[0]}.{segments[1]}.{b64url(signature)}"


@dataclass(frozen=True)
class InstallationToken:
    installation_id: int
    token: str
    expires_at: datetime
    repository_ids: tuple[int, ...] = ()
    permissions: Mapping[str, str] = field(default_factory=dict)

    def masked(self) -> str:
        return f"{self.token[:4]}*** (expires {self.expires_at.isoformat()})"


class TokenIssueError(Exception):
    """installation token 签发失败."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"GitHub token issue failed ({status}): {message}")
        self.status: int = status


def parse_github_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class InstallationTokenCache:
    """每个 installation 分别缓存, 剩余不足 5 分钟才刷新, 同一 installation 单飞签发."""

    def __init__(self, config: GitHubAppConfig, transport: HttpTransport, clock: Clock) -> None:
        self.config: GitHubAppConfig = config
        self.transport: HttpTransport = transport
        self.clock: Clock = clock
        self.tokens: dict[int, InstallationToken] = {}
        self.repo_installations: dict[str, int] = {}
        self.guard: threading.Lock = threading.Lock()
        self.locks: dict[int, threading.Lock] = {}

    def app_jwt(self) -> str:
        return build_app_jwt(self.config.private_key_pem, self.config.jwt_issuer(), self.clock())

    def is_fresh(self, token: InstallationToken) -> bool:
        return token.expires_at - self.clock() > TOKEN_REFRESH_MARGIN

    def lock_for(self, installation_id: int) -> threading.Lock:
        with self.guard:
            return self.locks.setdefault(installation_id, threading.Lock())

    def get(self, installation_id: int, *, force_refresh: bool = False) -> InstallationToken:
        cached: InstallationToken | None = self.tokens.get(installation_id)
        if cached is not None and not force_refresh and self.is_fresh(cached):
            return cached
        with self.lock_for(installation_id):
            cached = self.tokens.get(installation_id)
            if cached is not None and not force_refresh and self.is_fresh(cached):
                return cached
            issued: InstallationToken = self.issue(installation_id)
            self.tokens[installation_id] = issued
            return issued

    def issue(self, installation_id: int) -> InstallationToken:
        url: str = f"{GITHUB_API}/app/installations/{installation_id}/access_tokens"
        response: HttpResponse = self.transport.request(
            "POST", url, github_headers(self.app_jwt()), None
        )
        body: object = response.body
        if response.status != 201 or not isinstance(body, dict):
            raise TokenIssueError(response.status, str(body)[:200])
        repos: object = body.get("repositories") or []
        repo_ids: tuple[int, ...] = (
            tuple(int(item["id"]) for item in repos if isinstance(item, dict) and "id" in item)
            if isinstance(repos, list)
            else ()
        )
        perms: object = body.get("permissions") or {}
        return InstallationToken(
            installation_id=installation_id,
            token=str(body["token"]),
            expires_at=parse_github_time(str(body["expires_at"])),
            repository_ids=repo_ids,
            permissions={str(k): str(v) for k, v in perms.items()}
            if isinstance(perms, dict)
            else {},
        )

    def invalidate(self, installation_id: int) -> None:
        self.tokens.pop(installation_id, None)

    def forget_installation(self, installation_id: int) -> None:
        self.invalidate(installation_id)
        stale: list[str] = [r for r, i in self.repo_installations.items() if i == installation_id]
        for repo in stale:
            self.repo_installations.pop(repo, None)

    def remember_repos(self, installation_id: int, repo_full_names: list[str]) -> None:
        for repo in repo_full_names:
            self.repo_installations[repo.lower()] = installation_id

    def forget_repos(self, repo_full_names: list[str]) -> None:
        for repo in repo_full_names:
            self.repo_installations.pop(repo.lower(), None)

    def installation_for_repo(self, repo_full_name: str) -> int | None:
        """映射缺失时以 JWT 身份查询 GET /repos/{owner}/{repo}/installation, 404 返回 None."""
        known: int | None = self.repo_installations.get(repo_full_name.lower())
        if known is not None:
            return known
        url: str = f"{GITHUB_API}/repos/{repo_full_name}/installation"
        response: HttpResponse = self.transport.request(
            "GET", url, github_headers(self.app_jwt()), None
        )
        if response.status != 200 or not isinstance(response.body, dict):
            return None
        installation_id: int = int(response.body["id"])
        self.repo_installations[repo_full_name.lower()] = installation_id
        return installation_id

    def clear(self) -> None:
        self.tokens.clear()
        self.repo_installations.clear()
