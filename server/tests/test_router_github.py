"""R3 GitHub provider: 签名, 去重, envelope 映射, JWT, token 缓存, 错误分类."""

from __future__ import annotations

import json
from base64 import urlsafe_b64decode
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hx_email.api.impl.router.ingress.ingress_github import build_github_ingress_router
from hx_email.api.impl.router.ingress.ingress_queue import IngressWorker, MemoryDeliveryLedger
from hx_email.config import Settings
from hx_email.server.router.providers.github import (
    GitHubAppProvider,
    OutboundPayload,
    SessionRef,
    build_write_action,
    classify_response,
)
from hx_email.server.router.providers.impl.github.github_auth import (
    GitHubAppConfig,
    InstallationTokenCache,
    build_app_jwt,
    open_app_config,
    redact_app_config,
    seal_app_config,
)
from hx_email.server.router.providers.impl.github.github_events import (
    AppIdentity,
    map_event,
    sign_body,
    verify_signature,
)
from hx_email.server.router.providers.impl.github.github_http import (
    HttpResponse,
    TransportTimeoutError,
)

SECRET = "s3cret-webhook-value-at-least-32-bytes!"
NOW = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = KEY.private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
).decode()
CONFIG = GitHubAppConfig("1234", "Iv1.client", "hx-router", PEM, SECRET)
IDENTITY = AppIdentity("1234", "hx-router")


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, str], object]] = []
        self.routes: dict[tuple[str, str], list[HttpResponse | Exception]] = {}

    def add(self, method: str, url_part: str, *responses: HttpResponse | Exception) -> None:
        self.routes[(method, url_part)] = list(responses)

    def request(
        self, method: str, url: str, headers: Mapping[str, str], json_body: object | None
    ) -> HttpResponse:
        self.calls.append((method, url, dict(headers), json_body))
        for (m, part), queue in self.routes.items():
            if m == method and part in url:
                item = queue.pop(0) if len(queue) > 1 else queue[0]
                if isinstance(item, Exception):
                    raise item
                return item
        raise AssertionError(f"unexpected call {method} {url}")

    def count(self, url_part: str) -> int:
        return sum(1 for _, url, _, _ in self.calls if url_part in url)


def token_response(token: str, expires: datetime) -> HttpResponse:
    body = {"token": token, "expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ")}
    return HttpResponse(201, {}, body)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


def make_provider() -> tuple[GitHubAppProvider, FakeTransport, Clock]:
    transport, clock = FakeTransport(), Clock()
    transport.add("GET", "/repos/hx/HX-Email/installation", HttpResponse(200, {}, {"id": 99}))
    transport.add(
        "POST",
        "/app/installations/99/access_tokens",
        token_response("ghs_token1", NOW + timedelta(hours=1)),
    )
    return GitHubAppProvider(lambda _iid: CONFIG, transport, clock), transport, clock


def comment_payload() -> dict[str, object]:
    return {
        "action": "created",
        "installation": {"id": 99},
        "repository": {"id": 5, "full_name": "hx/HX-Email"},
        "sender": {"id": 583231, "login": "octocat", "type": "User"},
        "issue": {"number": 42, "title": "bug"},
        "comment": {
            "id": 2449601123,
            "body": "复现了, 附上日志",
            "created_at": "2026-11-02T13:31:00Z",
            "html_url": "https://github.com/hx/HX-Email/issues/42#c",
            "user": {"id": 583231, "login": "octocat", "type": "User"},
        },
    }


def client_for(sink: list[tuple[int, list[dict[str, object]]]]) -> tuple[TestClient, IngressWorker]:
    provider, _, _ = make_provider()
    ledger = MemoryDeliveryLedger()
    worker = IngressWorker(provider.parse_event, lambda i, e: sink.append((i, e)), ledger)
    app = FastAPI()
    app.include_router(build_github_ingress_router(provider, ledger, worker, lambda i: i == 7))
    return TestClient(app), worker


def post(
    client: TestClient,
    body: bytes,
    sig: str | None,
    delivery: str = "d-1",
    event: str = "issue_comment",
) -> int:
    headers = {
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery,
        "Content-Type": "application/json",
    }
    if sig is not None:
        headers["X-Hub-Signature-256"] = sig
    return client.post("/api/v1/router/ingress/github/7", content=body, headers=headers).status_code


# ---- 签名校验 ----


def test_signature_valid_and_invalid() -> None:
    body = b'{"a":1}'
    good = sign_body(SECRET.encode(), body)
    assert verify_signature((SECRET.encode(),), body, good)
    assert not verify_signature((SECRET.encode(),), body + b" ", good)
    assert not verify_signature((b"other",), body, good)
    assert not verify_signature((SECRET.encode(),), body, good.replace("sha256=", "sha1="))
    assert not verify_signature((SECRET.encode(),), body, None)
    assert not verify_signature((), body, good)
    assert verify_signature((b"new", SECRET.encode()), body, good)  # secret 轮换


def test_signature_uses_compare_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    import hmac as hmac_module

    seen: list[str] = []
    real = hmac_module.compare_digest
    monkeypatch.setattr(hmac_module, "compare_digest", lambda a, b: seen.append("x") or real(a, b))
    verify_signature((SECRET.encode(),), b"{}", sign_body(SECRET.encode(), b"{}"))
    assert seen


def test_endpoint_signature_statuses() -> None:
    sink: list[tuple[int, list[dict[str, object]]]] = []
    client, worker = client_for(sink)
    body = json.dumps(comment_payload()).encode()
    assert post(client, body, sign_body(b"wrong", body)) == 401
    assert post(client, body, None) == 401
    assert post(client, b"", None) == 401
    assert post(client, b"", sign_body(SECRET.encode(), b"")) == 400
    assert post(client, body, sign_body(SECRET.encode(), body)) == 202
    worker.drain()
    assert len(sink) == 1


def test_endpoint_unknown_instance_and_unhandled_event() -> None:
    client, _ = client_for([])
    body = b'{"zen":"x"}'
    sig = sign_body(SECRET.encode(), body)
    headers = {"X-GitHub-Event": "star", "X-GitHub-Delivery": "p", "X-Hub-Signature-256": sig}
    assert (
        client.post("/api/v1/router/ingress/github/8", content=body, headers=headers).status_code
        == 404
    )
    assert post(client, body, sig, event="star") == 204


# ---- 去重 ----


def test_same_delivery_only_stored_once() -> None:
    sink: list[tuple[int, list[dict[str, object]]]] = []
    client, worker = client_for(sink)
    body = json.dumps(comment_payload()).encode()
    sig = sign_body(SECRET.encode(), body)
    assert post(client, body, sig, delivery="dup-1") == 202
    assert post(client, body, sig, delivery="dup-1") == 200
    worker.drain()
    assert len(sink) == 1
    assert post(client, body, sig, delivery="dup-2") == 202
    worker.drain()
    assert len(sink) == 2


# ---- envelope 映射 ----


def test_issue_comment_created_envelope() -> None:
    out = map_event(7, "issue_comment", "d-9", comment_payload(), IDENTITY)
    assert len(out.envelopes) == 1
    env = out.envelopes[0]
    assert env["session"] == "github:7:issue:hx/HX-Email#42"
    assert env["session_type"] == "issue"
    assert env["platform"] == "github"
    assert env["sender"] == {"id": "583231", "name": "octocat", "is_self": False}
    assert env["text"] == "复现了, 附上日志"
    assert env["platform_message_id"] == "ic:2449601123"
    assert env["dedup_key"] == "ic:2449601123"
    assert env["reply_to"] == ""
    assert env["occurred_at"] == "2026-11-02T13:31:00Z"
    raw = env["raw"]
    assert isinstance(raw, dict)
    assert raw["gh_delivery"] == "d-9"
    assert raw["gh_installation_id"] == 99
    assert raw["gh_thread_kind"] == "issue"


def test_issues_opened_envelope() -> None:
    payload = {
        "action": "opened",
        "installation": {"id": 99},
        "repository": {"id": 5, "full_name": "hx/HX-Email"},
        "sender": {"id": 11, "login": "alice", "type": "User"},
        "issue": {
            "id": 777,
            "number": 43,
            "title": "登录失败",
            "body": "步骤如下",
            "created_at": "2026-11-02T10:00:00Z",
            "html_url": "u",
        },
    }
    env = map_event(7, "issues", "d-2", payload, IDENTITY).envelopes[0]
    assert env["session"] == "github:7:issue:hx/HX-Email#43"
    assert env["text"] == "登录失败\n\n步骤如下"
    assert env["platform_message_id"] == "is:777"
    assert env["sender"] == {"id": "11", "name": "alice", "is_self": False}
    assert env["occurred_at"] == "2026-11-02T10:00:00Z"


def test_non_created_actions_update_metadata() -> None:
    payload = comment_payload() | {"action": "edited"}
    out = map_event(7, "issue_comment", "d", payload, IDENTITY)
    # edited 覆盖同一 dedup_key 的正文 (docs/providers/github-app.md 3.1), 同时更新会话元数据
    assert out.envelopes[0]["edit"] is True
    assert out.session_updates[0]["session"] == "github:7:issue:hx/HX-Email#42"
    closed = {
        "action": "closed",
        "repository": {"full_name": "hx/HX-Email"},
        "issue": {"number": 42, "title": "bug", "state": "closed"},
    }
    out2 = map_event(7, "issues", "d", closed, IDENTITY)
    assert out2.envelopes[0]["kind"] == "thread_state"
    assert out2.session_updates[0]["state"] == "closed"
    assert (
        map_event(7, "pull_request_review", "d", {"action": "submitted"}, IDENTITY).envelopes == []
    )


def test_self_comment_marker_stripped() -> None:
    payload = comment_payload()
    comment = payload["comment"]
    assert isinstance(comment, dict)
    comment["body"] = "hi\n\n<!-- hx-router delivery=dl_5 -->"
    comment["user"] = {"id": 1, "login": "hx-router[bot]", "type": "Bot"}
    env = map_event(7, "issue_comment", "d", payload, IDENTITY).envelopes[0]
    assert env["text"] == "hi"
    assert env["sender"] == {"id": "1", "name": "hx-router[bot]", "is_self": True}


# ---- JWT ----


def test_app_jwt_header_and_claims() -> None:
    token = build_app_jwt(PEM, "Iv1.client", NOW)
    head, claims, sig = token.split(".")

    def dec(seg: str) -> dict[str, object]:
        return json.loads(urlsafe_b64decode(seg + "=" * (-len(seg) % 4)))

    assert dec(head) == {"alg": "RS256", "typ": "JWT"}
    issued = int(NOW.timestamp())
    assert dec(claims) == {"iat": issued - 60, "exp": issued + 540, "iss": "Iv1.client"}
    raw_sig = urlsafe_b64decode(sig + "=" * (-len(sig) % 4))
    KEY.public_key().verify(
        raw_sig, f"{head}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256()
    )


def test_config_seal_roundtrip_and_redaction(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    sealed = seal_app_config(settings, CONFIG)
    assert sealed.startswith("enc:v1:") and SECRET not in sealed and "PRIVATE KEY" not in sealed
    assert open_app_config(settings, sealed) == CONFIG
    redacted = redact_app_config(CONFIG)
    assert redacted["private_key_pem"] == "***" and redacted["webhook_secret"] == "***"
    assert redacted["app_id"] == "1234"


# ---- installation token 缓存 ----


def test_token_cache_reuses_until_five_minutes_before_expiry() -> None:
    transport, clock = FakeTransport(), Clock()
    transport.add(
        "POST",
        "/app/installations/1/access_tokens",
        token_response("t1", NOW + timedelta(hours=1)),
        token_response("t2", NOW + timedelta(hours=2)),
    )
    transport.add(
        "POST",
        "/app/installations/2/access_tokens",
        token_response("other", NOW + timedelta(hours=1)),
    )
    cache = InstallationTokenCache(CONFIG, transport, clock)
    assert cache.get(1).token == "t1"
    clock.now = NOW + timedelta(minutes=54)
    assert cache.get(1).token == "t1"
    assert transport.count("/installations/1/") == 1
    assert cache.get(2).token == "other"  # 多 installation 分别缓存
    clock.now = NOW + timedelta(minutes=55, seconds=1)
    assert cache.get(1).token == "t2"
    assert transport.count("/installations/1/") == 2
    auth = transport.calls[0][2]["Authorization"]
    assert auth.startswith("Bearer ") and auth.count(".") == 2


# ---- 发送与错误分类 ----


def session(address: str) -> SessionRef:
    parts = address.split(":", 3)
    return SessionRef(address, "github", 7, parts[2], parts[3], "")


def test_send_issue_comment_appends_marker() -> None:
    provider, transport, _ = make_provider()
    transport.add("POST", "/issues/42/comments", HttpResponse(201, {}, {"id": 555}))
    result = provider.send(
        session("github:7:issue:hx/HX-Email#42"), OutboundPayload("dl_1", "hello", "", "")
    )
    assert result.status == "sent" and result.platform_message_id == "ic:555"
    _method, url, headers, body = transport.calls[-1]
    assert url == "https://api.github.com/repos/hx/HX-Email/issues/42/comments"
    assert headers["Authorization"] == "Bearer ghs_token1"
    assert body == {"body": "hello\n\n<!-- hx-router delivery=dl_1 -->"}


def test_write_action_routing() -> None:
    reply = build_write_action(
        session("github:7:issue:hx/HX-Email#8"), OutboundPayload("d", "t", "rc:31", "")
    )
    assert reply is not None and reply.kind == "reply_review_comment"
    assert reply.reply_to_comment_id == 31
    assert (
        build_write_action(session("github:7:repo:hx/HX-Email"), OutboundPayload("d", "t", "", ""))
        is None
    )
    issue = build_write_action(
        session("github:7:repo:hx/HX-Email"), OutboundPayload("d", "t", "", "Title")
    )
    assert issue is not None and issue.kind == "open_issue"


@pytest.mark.parametrize(
    ("status", "headers", "body", "expected", "code", "retry_after"),
    [
        (502, {}, {}, "retry", "provider_error", 0),
        (503, {}, {}, "retry", "provider_error", 0),
        (
            403,
            {"Retry-After": "30"},
            {"message": "secondary rate limit"},
            "retry",
            "rate_limited",
            30,
        ),
        (
            403,
            {},
            {"message": "You have exceeded a secondary rate limit"},
            "retry",
            "rate_limited",
            60,
        ),
        (
            403,
            {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(int(NOW.timestamp()) + 120)},
            {"message": "API rate limit exceeded"},
            "retry",
            "rate_limited",
            120,
        ),
        (429, {"Retry-After": "5000"}, {}, "retry", "rate_limited", 900),
        (
            403,
            {},
            {"message": "Resource not accessible by integration"},
            "failed",
            "permission_denied",
            0,
        ),
        (403, {}, {"message": "abuse detection mechanism"}, "failed", "abuse_detected", 0),
        (404, {}, {"message": "Not Found"}, "failed", "not_found", 0),
        (422, {}, {"message": "Validation Failed"}, "failed", "unprocessable", 0),
    ],
)
def test_error_classification(
    status: int,
    headers: dict[str, str],
    body: dict[str, str],
    expected: str,
    code: str,
    retry_after: int,
) -> None:
    result = classify_response(HttpResponse(status, headers, body), int(NOW.timestamp()), "ic")
    assert result.status == expected
    assert result.error_code == code
    assert result.retryable is (expected == "retry")
    assert result.retry_after_seconds == retry_after
    assert result.risk_signal is (code == "abuse_detected")


def test_send_401_refreshes_token_once_and_timeout_is_unknown() -> None:
    provider, transport, _ = make_provider()
    transport.add(
        "POST", "/issues/42/comments", HttpResponse(401, {}, {}), HttpResponse(201, {}, {"id": 9})
    )
    result = provider.send(
        session("github:7:issue:hx/HX-Email#42"), OutboundPayload("dl", "x", "", "")
    )
    assert result.status == "sent"
    assert transport.count("/access_tokens") == 2
    transport.add("POST", "/issues/42/comments", TransportTimeoutError("read timeout"))
    timed_out = provider.send(
        session("github:7:issue:hx/HX-Email#42"), OutboundPayload("dl2", "x", "", "")
    )
    assert timed_out.status == "unknown"


def test_reconcile_unknown_finds_marker() -> None:
    provider, transport, _ = make_provider()
    transport.add(
        "GET",
        "/issues/42/comments",
        HttpResponse(
            200,
            {},
            [
                {"id": 1, "body": "other"},
                {"id": 2, "body": "x\n\n<!-- hx-router delivery=dl_7 -->"},
            ],
        ),
    )
    found = provider.reconcile_unknown(session("github:7:issue:hx/HX-Email#42"), "dl_7")
    assert found.status == "sent" and found.platform_message_id == "ic:2"
    transport.add("GET", "/pulls/42/comments", HttpResponse(404, {}, {}))
    missing = provider.reconcile_unknown(session("github:7:issue:hx/HX-Email#42"), "dl_8")
    assert missing.status == "retry" and missing.error_code == "marker_not_found"
