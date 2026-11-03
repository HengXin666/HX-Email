"""GitHub App Manifest one-click flow over real HTTP, with a fake api.github.com.

Each test is written to fail on a plausible wrong implementation: extra permissions or
events in the manifest, a state that can be replayed or outlives 10 minutes, a code spent
before the encryption key is checked, or a management response that echoes the PEM.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from hx_email.api.impl.router import github_connect as connect_support
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.messaging.registry import clear_runtime
from hx_email.server.router.providers.impl import github_manifest
from hx_email.server.router.providers.impl.github.github_auth import (
    GitHubAppConfig,
    open_app_config,
)
from hx_email.server.router.providers.impl.github.github_http import HttpResponse
from hx_email.server.router.providers.impl.github_manifest import (
    ManifestError,
    build_manifest,
    consume_state,
    save_state,
)

API = "/api/v1"
BASE = "https://hx.example.com"


def make_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()


PEM = make_pem()
PEM_BODY_LINES = [line for line in PEM.splitlines() if line and "-----" not in line]


class FakeGitHub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.conversion_status = 201

    def request(
        self, method: str, url: str, headers: dict[str, str], body: dict[str, object] | None
    ) -> HttpResponse:
        self.calls.append((method, url))
        if "/app-manifests/" in url:
            if self.conversion_status != 201:
                return HttpResponse(self.conversion_status, {}, {"message": "Not Found"})
            return HttpResponse(
                201,
                {},
                {
                    "id": 424242,
                    "slug": "hx-email-abc123",
                    "client_id": "Iv1.client",
                    "client_secret": "client-secret-never-stored",
                    "webhook_secret": "hook-secret",
                    "pem": PEM,
                    "owner": {"login": "hx"},
                },
            )
        assert headers["Authorization"].startswith("Bearer ey")
        if url.endswith("/app"):
            return HttpResponse(200, {}, {"id": 424242, "slug": "hx-email-abc123", "name": "x"})
        if "/app/installations?" in url:
            return HttpResponse(200, {}, [{"id": 99, "account": {"login": "hx"}}])
        if url.endswith("/app/installations/99"):
            return HttpResponse(200, {}, {"id": 99, "account": {"login": "hx"}})
        return HttpResponse(404, {}, {"message": "Not Found"})


@pytest.fixture()
def github(monkeypatch: pytest.MonkeyPatch) -> Any:
    fake = FakeGitHub()
    monkeypatch.setattr(connect_support, "default_transport", lambda: fake)
    clear_runtime()
    yield fake
    clear_runtime()


@pytest.fixture()
def env(tmp_path: Any, github: FakeGitHub) -> tuple[TestClient, Settings, dict[str, str]]:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    session = client.post(
        f"{API}/auth/login", json={"username": "admin", "password": "admin"}
    ).json()
    return client, settings, {"Authorization": f"Bearer {session['access_token']}"}


def start(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.get(
        f"{API}/router/github/manifest", params={"base_url": BASE + "/"}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def callback(client: TestClient, state: str, code: str = "abc123") -> str:
    response = client.get(
        f"{API}/router/github/callback",
        params={"code": code, "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 302
    return str(response.headers["location"])


def stored_config(settings: Settings, instance_id: int) -> GitHubAppConfig:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT config_encrypted FROM messaging_instances WHERE id = ?", (instance_id,)
        ).fetchone()
    return open_app_config(settings, str(row["config_encrypted"]))


def test_manifest_permissions_and_events_are_exact() -> None:
    manifest = build_manifest(BASE, "abc123", 7)
    assert manifest["default_permissions"] == {
        "metadata": "read",
        "issues": "write",
        "pull_requests": "write",
    }
    assert sorted(manifest["default_events"]) == sorted(  # type: ignore[arg-type]
        ["issue_comment", "pull_request_review", "pull_request_review_comment", "issues"]
    )
    assert "installation" not in manifest["default_events"]  # type: ignore[operator]
    assert "installation_repositories" not in manifest["default_events"]  # type: ignore[operator]
    assert manifest["public"] is False
    assert manifest["name"] == "hx-email-abc123"
    assert manifest["hook_attributes"] == {
        "url": f"{BASE}/api/v1/router/ingress/github/7",
        "active": True,
    }
    assert manifest["redirect_url"] == f"{BASE}/api/v1/router/github/callback"


def test_manifest_endpoint_requires_admin(env: Any) -> None:
    client, _settings, _headers = env
    assert client.get(f"{API}/router/github/manifest").status_code == 401


def test_manifest_endpoint_returns_action_and_state(env: Any) -> None:
    client, _settings, headers = env
    data = start(client, headers)
    assert data["action"] == f"https://github.com/settings/apps/new?state={data['state']}"
    assert len(data["state"]) >= 40
    hook = data["manifest"]["hook_attributes"]["url"]
    assert hook == f"{BASE}/api/v1/router/ingress/github/{data['instance_id']}"


def test_callback_success_encrypts_config(env: Any, github: FakeGitHub) -> None:
    client, settings, headers = env
    data = start(client, headers)
    location = callback(client, data["state"])
    assert location.startswith("/messaging?connected=1&slug=hx-email-abc123")
    config = stored_config(settings, data["instance_id"])
    assert config.app_id == "424242"
    assert config.app_slug == "hx-email-abc123"
    assert config.client_id == "Iv1.client"
    assert config.private_key_pem == PEM
    assert config.webhook_secret == "hook-secret"
    with connect(settings) as connection:
        raw = connection.execute("SELECT config_encrypted FROM messaging_instances").fetchone()
    assert "BEGIN RSA" not in raw[0] and "client-secret-never-stored" not in raw[0]


def test_state_is_single_use(env: Any, github: FakeGitHub) -> None:
    client, _settings, headers = env
    data = start(client, headers)
    assert "connected=1" in callback(client, data["state"])
    assert "error=invalid_state" in callback(client, data["state"])
    assert sum("/app-manifests/" in url for _m, url in github.calls) == 1


def test_state_expires_after_ten_minutes(tmp_path: Any) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    issued = datetime(2026, 11, 3, 1, 0, tzinfo=UTC)
    save_state(settings, "fresh", 1, issued)
    save_state(settings, "stale", 1, issued)
    assert consume_state(settings, "fresh", issued + timedelta(minutes=9)) == 1
    with pytest.raises(ManifestError) as caught:
        consume_state(settings, "stale", issued + timedelta(minutes=11))
    assert caught.value.reason == "invalid_state"


def test_failed_conversion_leaves_state_used(env: Any, github: FakeGitHub) -> None:
    """state 在花 code 前就被消费: code 一次性, 兑换失败后重放同一个 state 也不该再打 GitHub."""
    client, settings, headers = env
    data = start(client, headers)
    github.conversion_status = 404
    assert "error=conversion_failed" in callback(client, data["state"])
    with connect(settings) as connection:
        used = connection.execute(
            "SELECT used FROM router_github_app_states WHERE state = ?", (data["state"],)
        ).fetchone()[0]
    assert used == 1
    github.conversion_status = 201
    assert "error=invalid_state" in callback(client, data["state"])
    assert sum("/app-manifests/" in url for _m, url in github.calls) == 1


def test_code_not_spent_when_encryption_unavailable(
    env: Any, github: FakeGitHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, settings, headers = env
    data = start(client, headers)

    def broken(_settings: Settings, _value: str) -> str:
        raise OSError("key file unreadable")

    monkeypatch.setattr(github_manifest, "encrypt_secret", broken)
    assert "error=encryption_unavailable" in callback(client, data["state"])
    assert github.calls == []
    with connect(settings) as connection:
        used = connection.execute(
            "SELECT used FROM router_github_app_states WHERE state = ?", (data["state"],)
        ).fetchone()[0]
    assert used == 0


def test_management_endpoints_never_echo_pem(env: Any) -> None:
    client, _settings, headers = env
    data = start(client, headers)
    callback(client, data["state"])
    ref = {"instance_id": data["instance_id"]}
    verified = client.post(f"{API}/router/github/verify", json=ref, headers=headers)
    attached = client.post(
        f"{API}/router/github/installations/99/attach", json=ref, headers=headers
    )
    listed = client.get(f"{API}/messaging/instances", headers=headers)
    assert verified.status_code == 200 and attached.status_code == 200
    assert verified.json()["verified"] is True
    assert verified.json()["installations"][0]["id"] == 99
    assert verified.json()["app_config"]["has_private_key"] is True
    assert attached.json()["installation"]["id"] == 99
    for response in (verified, attached, listed):
        text = response.text
        assert "PRIVATE KEY" not in text
        assert "hook-secret" not in text
        assert not any(line in text for line in PEM_BODY_LINES)


def test_attach_rejects_foreign_installation(env: Any) -> None:
    client, _settings, headers = env
    data = start(client, headers)
    callback(client, data["state"])
    response = client.post(
        f"{API}/router/github/installations/12345/attach",
        json={"instance_id": data["instance_id"]},
        headers=headers,
    )
    assert response.status_code == 404
