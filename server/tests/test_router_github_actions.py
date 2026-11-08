"""GitHub 出站动作: comment_create 与 reaction_add 经 action_invoke 走 outbox 到 provider."""

from __future__ import annotations

import sqlite3
import time
import types
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from hx_email.api.impl.gateway.mcp_tools import call_tool
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.gateway.impl import dispatch as dispatch_module
from hx_email.server.gateway.impl.breaker import BREAKER
from hx_email.server.gateway.providers import HUB, SHAPER
from hx_email.server.messaging.registry import clear_runtime
from hx_email.server.router.provider import ActionCall, SessionRef
from hx_email.server.router.providers.github import GitHubAppProvider
from hx_email.server.router.providers.impl.github.github_auth import (
    GitHubAppConfig,
    seal_app_config,
)
from hx_email.server.router.providers.impl.github.github_http import (
    HttpResponse,
    TransportTimeoutError,
)
from hx_email.server.router.providers.impl.github_reactions import reaction_request

API = "/api/v1"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = KEY.private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
).decode()
CONFIG = GitHubAppConfig("1234", "Iv1.client", "hx-router", PEM, "s" * 40)
BASE = "https://api.github.com/repos/hx/HX-Email"


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []
        self.routes: list[tuple[str, str, HttpResponse | Exception]] = []
        expires = (datetime.now(UTC) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.add("GET", "/repos/hx/HX-Email/installation", HttpResponse(200, {}, {"id": 99}))
        self.add(
            "POST",
            "/app/installations/99/access_tokens",
            HttpResponse(201, {}, {"token": "ghs_t", "expires_at": expires}),
        )

    def add(self, method: str, url_part: str, response: HttpResponse | Exception) -> None:
        self.routes.insert(0, (method, url_part, response))

    def request(
        self, method: str, url: str, headers: Mapping[str, str], body: object | None
    ) -> HttpResponse:
        self.calls.append((method, url, body))
        for route_method, part, response in self.routes:
            if route_method == method and part in url:
                if isinstance(response, Exception):
                    raise response
                return response
        raise AssertionError(f"unexpected call {method} {url}")

    def posted(self, url_part: str) -> list[object]:
        return [body for method, url, body in self.calls if method == "POST" and url_part in url]


def ref(number: int) -> SessionRef:
    address = f"github:7:issue:hx/HX-Email#{number}"
    return SessionRef(address, "github", 7, "issue", f"hx/HX-Email#{number}", "")


def test_reaction_request_targets() -> None:
    address = "github:7:issue:hx/HX-Email#42"
    thread = reaction_request(address, {"content": "+1"})
    issue_comment = reaction_request(address, {"content": "eyes", "message_id": "ic:5"})
    review_comment = reaction_request(address, {"content": "heart", "message_id": "rc:6"})
    assert thread is not None and thread.url == f"{BASE}/issues/42/reactions"
    assert issue_comment is not None and issue_comment.url == f"{BASE}/issues/comments/5/reactions"
    assert review_comment is not None
    assert review_comment.url == f"{BASE}/pulls/comments/6/reactions"
    assert review_comment.body == {"content": "heart"}
    assert reaction_request(address, {"content": "+1", "message_id": "dc:1"}) is None
    assert reaction_request("github:7:repo:hx/HX-Email", {"content": "+1"}) is None


def test_provider_invoke_comment_reaction_and_timeout() -> None:
    transport = FakeTransport()
    provider = GitHubAppProvider(lambda _iid: CONFIG, transport)
    transport.add("POST", "/issues/42/comments", HttpResponse(201, {}, {"id": 555}))
    comment = provider.invoke(ref(42), ActionCall("d_1", "comment_create", {"text": "hi"}))
    assert comment.status == "sent" and comment.platform_message_id == "ic:555"
    assert transport.posted("/issues/42/comments") == [
        {"body": "hi\n\n<!-- hx-router delivery=d_1 -->"}
    ]
    transport.add("POST", "/issues/42/reactions", HttpResponse(200, {}, {"id": 9}))
    again = provider.invoke(ref(42), ActionCall("d_2", "reaction_add", {"content": "+1"}))
    assert again.status == "sent" and again.platform_message_id == "re:9"
    transport.add("POST", "/issues/43/reactions", TransportTimeoutError("slow"))
    slow = provider.invoke(ref(43), ActionCall("d_3", "reaction_add", {"content": "+1"}))
    assert slow.status == "retry" and slow.error_code == "provider_timeout"
    unknown = provider.invoke(ref(42), ActionCall("d_4", "discussion_create", {}))
    assert unknown.status == "failed" and unknown.error_code == "action_not_supported"


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    clear_runtime()
    HUB.clear()
    BREAKER.clear()
    SHAPER._buckets.clear()
    SHAPER._holds.clear()
    monkeypatch.setattr(
        dispatch_module,
        "time",
        types.SimpleNamespace(sleep=lambda _s: None, monotonic=time.monotonic),
    )
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings), raise_server_exceptions=False)
    token = client.post(
        f"{API}/auth/login", json={"username": "admin", "password": "admin"}
    ).json()["access_token"]
    with connect(settings) as connection:
        user_id = int(connection.execute("SELECT id FROM users LIMIT 1").fetchone()[0])
        cursor: sqlite3.Cursor = connection.execute(
            "INSERT INTO messaging_instances (user_id, kind, name, config_encrypted) "
            "VALUES (?, 'github', 'gh', ?)",
            (user_id, seal_app_config(settings, CONFIG)),
        )
        connection.commit()
    transport = FakeTransport()
    HUB.github = GitHubAppProvider(lambda _iid: CONFIG, transport)
    yield {
        "client": client,
        "headers": {"Authorization": f"Bearer {token}"},
        "settings": settings,
        "user_id": user_id,
        "gh": int(cursor.lastrowid or 0),
        "transport": transport,
    }
    clear_runtime()
    HUB.clear()


def test_capabilities_declare_actions_with_params(env: dict[str, Any]) -> None:
    caps = env["client"].get(
        f"{API}/router/capabilities", params={"platform": "github"}, headers=env["headers"]
    )
    actions = {a["name"]: a for a in caps.json()["platforms"][0]["actions"]}
    assert {"message_send", "comment_create", "reaction_add"} <= set(actions)
    reaction = {p["name"]: p for p in actions["reaction_add"]["params"]}
    assert reaction["content"]["required"] is True and "rocket" in reaction["content"]["choices"]
    assert actions["comment_create"]["requires"] == ["issues:write", "pull_requests:write"]


def test_actions_over_rest_and_mcp(env: dict[str, Any]) -> None:
    client, headers, gh, transport = env["client"], env["headers"], env["gh"], env["transport"]
    transport.add("POST", "/issues/42/comments", HttpResponse(201, {}, {"id": 555}))
    transport.add("POST", "/issues/comments/555/reactions", HttpResponse(201, {}, {"id": 77}))
    transport.add("POST", "/issues/44/reactions", HttpResponse(201, {}, {"id": 78}))
    body = {
        "target": f"github:{gh}/repo/hx/HX-Email/issue/42",
        "action": "comment_create",
        "params": {"text": "收到, 在看"},
        "idempotency_key": "act-00000001",
    }
    first = client.post(f"{API}/router/actions", json=body, headers=headers).json()
    assert first["status"] == "sent", first
    assert first["action"] == "comment_create" and first["platform_message_id"] == "ic:555"
    repeat = client.post(f"{API}/router/actions", json=body, headers=headers).json()
    assert repeat["deduplicated"] is True and len(transport.posted("/issues/42/comments")) == 1
    reacted = client.post(
        f"{API}/router/actions",
        json={
            "target": f"github:{gh}:issue:hx/HX-Email#43",
            "action": "reaction_add",
            "params": {"content": "heart", "message_id": "ic:555"},
            "idempotency_key": "act-00000002",
        },
        headers=headers,
    ).json()
    assert reacted["status"] == "sent" and reacted["platform_message_id"] == "re:77", reacted
    assert transport.posted("/issues/comments/555/reactions") == [{"content": "heart"}]
    via_mcp = call_tool(
        env["settings"],
        env["user_id"],
        "action_invoke",
        {
            "target": f"github:{gh}:issue:hx/HX-Email#44",
            "action": "reaction_add",
            "params": {"content": "rocket"},
            "idempotency_key": "act-00000003",
        },
    )
    assert via_mcp["status"] == "sent" and via_mcp["platform_message_id"] == "re:78"


@pytest.mark.parametrize(
    ("target_suffix", "action", "params", "code"),
    [
        (":issue:hx/HX-Email#42", "reaction_add", {"content": "smile"}, "invalid_payload"),
        (":issue:hx/HX-Email#42", "reaction_add", {}, "invalid_payload"),
        (":issue:hx/HX-Email#42", "comment_create", {"text": "x", "x": "1"}, "invalid_payload"),
        (
            ":issue:hx/HX-Email#42",
            "reaction_add",
            {"content": "+1", "message_id": "dc:1"},
            "invalid_payload",
        ),
        (":repo:hx/HX-Email", "comment_create", {"text": "x"}, "action_not_supported"),
        (":issue:hx/HX-Email#42", "discussion_create", {"text": "x"}, "action_not_supported"),
    ],
)
def test_invalid_actions_are_422(
    env: dict[str, Any], target_suffix: str, action: str, params: dict[str, str], code: str
) -> None:
    response = env["client"].post(
        f"{API}/router/actions",
        json={
            "target": f"github:{env['gh']}{target_suffix}",
            "action": action,
            "params": params,
            "idempotency_key": "bad-00000001",
        },
        headers=env["headers"],
    )
    assert response.status_code == 422 and response.json()["error"]["code"] == code
    assert env["transport"].posted("/repos/hx/HX-Email/") == []
