"""HTTP transport for the GitHub App provider: one seam, three outcomes.

Everything that touches the network goes through ``HttpTransport.request`` so tests
drive the provider with an in-memory fake instead of monkeypatching ``requests``.
The three failure modes that matter to the outbox are separated here:

- ``TransportTimeoutError``: the request may have been delivered. The outbox must
  treat this as ``unknown`` and reconcile by marker, never as a retry.
- ``TransportConnectError``: nothing left the machine. Safe to retry.
- an ``HttpResponse``: GitHub answered, so ``classify_response`` decides.

``classify_response`` encodes the retry matrix from docs/providers/github-app.md 6.2:
403 with a rate-limit body is retryable with ``retry_after_seconds``, 5xx is retryable,
401/404/422 are terminal because a retry cannot change the answer.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Final, Protocol

import requests

from hx_email.server.router.provider import SendResult

GITHUB_API: Final[str] = "https://api.github.com"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 20.0
SERVER_ERROR_FLOOR: Final[int] = 500
RATE_LIMIT_STATUS: Final[int] = 429
FORBIDDEN_STATUS: Final[int] = 403
MAX_DETAIL_CHARS: Final[int] = 300


class TransportTimeoutError(Exception):
    """Request left the machine but no response came back in time."""


class TransportConnectError(Exception):
    """Request never left the machine; safe to retry immediately."""


@dataclass(frozen=True)
class HttpResponse:
    """A decoded GitHub response; ``body`` is whatever JSON came back, or {}."""

    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: object = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return self.body if isinstance(self.body, dict) else {}


class HttpTransport(Protocol):
    """The only network seam the provider has."""

    def request(
        self, method: str, url: str, headers: dict[str, str], body: dict[str, object] | None
    ) -> HttpResponse: ...


def github_headers(token: str) -> dict[str, str]:
    """Headers GitHub requires: bearer token, explicit API version, JSON body."""
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "hx-email-router",
    }


class RequestsTransport:
    """Real transport backed by ``requests``; the only place that imports it."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.timeout: float = timeout

    def request(
        self, method: str, url: str, headers: dict[str, str], body: dict[str, object] | None
    ) -> HttpResponse:
        try:
            response = requests.request(
                method, url, headers=headers, json=body, timeout=self.timeout
            )
        except requests.Timeout as error:
            raise TransportTimeoutError(str(error)) from error
        except requests.ConnectionError as error:
            raise TransportConnectError(str(error)) from error
        try:
            decoded: object = response.json()
        except ValueError:
            decoded = {}
        return HttpResponse(
            status=response.status_code,
            headers={key.lower(): value for key, value in response.headers.items()},
            body=decoded,
        )


def failed(code: str, message: str) -> SendResult:
    """Terminal failure: a retry cannot change the answer."""
    return SendResult(status="failed", error_code=code, error_message=message)


def retryable(code: str, message: str) -> SendResult:
    """Nothing reached GitHub, or repeating the call is harmless: try again later."""
    return SendResult(status="retry", retryable=True, error_code=code, error_message=message)


def header_value(headers: dict[str, str], name: str) -> str:
    """Header lookup is case-insensitive: HTTP names are, and callers pass raw dicts."""
    lowered: str = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value.strip()
    return ""


def retry_after_seconds(
    headers: dict[str, str], body: dict[str, object], now_epoch: int | None = None
) -> int:
    """GitHub signals the wait either as a header pair or inside the message text."""
    header: str = header_value(headers, "retry-after")
    if header.isdigit():
        return max(1, min(900, int(header)))
    reset: str = header_value(headers, "x-ratelimit-reset")
    if reset.isdigit():
        # ``x-ratelimit-reset`` is an absolute epoch second, so the wait is the delta
        # against the caller's clock, not against wall time.
        reference: float = float(now_epoch) if now_epoch is not None else time.time()
        return max(1, min(900, int(reset) - int(reference)))
    del body
    return 60


def is_rate_limited(response: HttpResponse) -> bool:
    """A 403 is retryable only when the text says rate limit, never for permissions."""
    if response.status == RATE_LIMIT_STATUS:
        return True
    body: dict[str, object] = response.as_dict()
    message: str = str(body.get("message", "")).lower()
    return "rate limit" in message


def is_abuse(response: HttpResponse) -> bool:
    """Abuse detection is a risk signal: the account is held, the message is not retried."""
    message: str = str(response.as_dict().get("message", "")).lower()
    return "abuse" in message


# 终态失败带上 GitHub 自己的原因 (message 与 errors[]), 否则调用方只看到状态码, 不知道该改什么;
# 例如 422 "Review Can not approve your own pull request". 截断到 MAX_DETAIL_CHARS, 不存整个响应
# 决策记录: .agents/notes/implemented/feature/2026-11-09-github-user-live-fixes.md
def github_detail(body: dict[str, object]) -> str:
    """``message`` plus the ``errors`` entries GitHub sends with 4xx answers, one short line."""
    parts: list[str] = []
    message: str = str(body.get("message") or "").strip()
    if message:
        parts.append(message)
    errors: object = body.get("errors")
    for item in errors if isinstance(errors, list) else []:
        raw: object = (item.get("message") or item.get("code")) if isinstance(item, dict) else item
        text: str = str(raw or "").strip()
        if text and text not in parts:
            parts.append(text)
    return "; ".join(parts)[:MAX_DETAIL_CHARS]


def with_detail(text: str, response: HttpResponse) -> str:
    detail: str = github_detail(response.as_dict())
    return f"{text}: {detail}" if detail else text


def classify_response(response: HttpResponse, now_epoch: int, prefix: str) -> SendResult:
    """Map a GitHub answer onto the outbox retry matrix (spec 6.2)."""
    if 200 <= response.status < 300:
        raw_id: object = response.as_dict().get("id", "")
        platform_id: str = f"{prefix}:{raw_id}" if raw_id != "" else ""
        return SendResult(status="sent", platform_message_id=platform_id)
    if is_abuse(response):
        return SendResult(
            status="failed",
            risk_signal=True,
            error_code="abuse_detected",
            error_message="GitHub flagged abuse; the installation is held",
        )
    if is_rate_limited(response):
        return SendResult(
            status="retry",
            retryable=True,
            error_code="rate_limited",
            error_message=f"GitHub rate limit, HTTP {response.status}",
            retry_after_seconds=retry_after_seconds(
                response.headers, response.as_dict(), now_epoch
            ),
        )
    if response.status >= SERVER_ERROR_FLOOR:
        return SendResult(
            status="retry",
            retryable=True,
            error_code="provider_error",
            error_message=f"GitHub returned HTTP {response.status}",
        )
    if response.status in (401, FORBIDDEN_STATUS):
        return SendResult(
            status="failed",
            error_code="permission_denied",
            error_message=with_detail(f"GitHub refused: HTTP {response.status}", response),
        )
    if response.status == 404:
        return SendResult(
            status="failed",
            error_code="not_found",
            error_message=with_detail("repository or thread is gone", response),
        )
    if response.status == 422:
        return SendResult(
            status="failed",
            error_code="unprocessable",
            error_message=with_detail("GitHub rejected the payload as unprocessable", response),
        )
    return SendResult(
        status="failed",
        error_code="provider_error",
        error_message=f"GitHub returned HTTP {response.status}",
    )
