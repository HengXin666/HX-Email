"""End-to-end ingress: a signed GitHub webhook really lands in messaging_messages.

These tests drive the assembled router over HTTP rather than calling functions, because
the failure this guards against is precisely "the endpoint exists but is not wired":
before `assembly.py`, `ingress_github.py` was dead code and every webhook 404'd.

The signature is computed with the same HMAC the provider verifies, so a pass here
proves the whole chain: HTTP -> signature -> dedup ledger -> async worker -> parse ->
validate -> store -> readable through the cursor.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hx_email.api.impl.router.assembly import build_github_ingress
from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.models.messaging import migrate_messaging_schema
from hx_email.server.router.impl.reader import latest_cursor, read_messages
from hx_email.server.router.providers.impl.github.github_auth import (
    GitHubAppConfig,
    seal_app_config,
)

WEBHOOK_SECRET = "s3cr3t-webhook"
APP_ID = "12345"
PATIENCE_SECONDS = 5.0


def make_settings(tmp_path: Path) -> Settings:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    with connect(settings) as connection:
        migrate_messaging_schema(connection)
        connection.commit()
    return settings


def add_github_instance(settings: Settings, user_id: int = 1) -> int:
    config = GitHubAppConfig(
        app_id=APP_ID,
        client_id="Iv1.abc",
        app_slug="hx-router",
        private_key_pem=(
            "-----BEGIN RSA PRIVATE KEY-----\nnot-a-real-key\n-----END RSA PRIVATE KEY-----\n"
        ),
        webhook_secret=WEBHOOK_SECRET,
    )
    with connect(settings) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO users (id, username, password_hash) VALUES (?, ?, ?)",
            (user_id, f"user{user_id}", "x"),
        )
        cursor: sqlite3.Cursor = connection.execute(
            "INSERT INTO messaging_instances (user_id, kind, name, config_encrypted) "
            "VALUES (?, 'github', 'gh', ?)",
            (user_id, seal_app_config(settings, config)),
        )
        connection.commit()
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


def issue_comment_payload(instance_id: int, comment_id: int = 555) -> dict[str, object]:
    return {
        "action": "created",
        "installation": {"id": 777},
        "repository": {"full_name": "hx/HX-Email", "owner": {"login": "hx"}},
        "sender": {"id": 9, "login": "alice"},
        "comment": {
            "id": comment_id,
            "body": "hello from a real webhook",
            "created_at": "2026-11-02T15:20:05Z",
            "html_url": "https://github.com/hx/HX-Email/issues/42#issuecomment-555",
            "user": {"id": 9, "login": "alice"},
        },
        "issue": {"number": 42, "title": "a thread"},
    }


@pytest.fixture()
def client(tmp_path: Path) -> Iterator[tuple[TestClient, Settings, int]]:
    settings = make_settings(tmp_path)
    instance_id = add_github_instance(settings)
    router, _worker = build_github_ingress(settings)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as test_client:
        yield test_client, settings, instance_id


def post(client: TestClient, instance_id: int, payload: dict[str, object], **headers: str) -> int:
    body: bytes = json.dumps(payload).encode()
    merged: dict[str, str] = {
        "X-GitHub-Event": "issue_comment",
        "X-GitHub-Delivery": headers.pop("delivery", "d-0001"),
        "X-Hub-Signature-256": headers.pop("signature", sign(body)),
        "Content-Type": "application/json",
    }
    merged.update(headers)
    response = client.post(
        f"/api/v1/router/ingress/github/{instance_id}", content=body, headers=merged
    )
    return response.status_code


def wait_for_messages(settings: Settings, user_id: int, source: str, count: int = 1) -> list:
    deadline: float = time.monotonic() + PATIENCE_SECONDS
    while time.monotonic() < deadline:
        page = read_messages(settings, user_id, source, "")
        if len(page.messages) >= count:
            return page.messages
        time.sleep(0.05)
    return read_messages(settings, user_id, source, "").messages


def test_signed_webhook_is_accepted_and_stored(client: tuple[TestClient, Settings, int]) -> None:
    test_client, settings, instance_id = client
    assert post(test_client, instance_id, issue_comment_payload(instance_id)) == 202
    messages = wait_for_messages(settings, 1, f"github:{instance_id}:issue:hx/HX-Email#42")
    assert len(messages) == 1
    stored = messages[0]
    assert stored.text == "hello from a real webhook"
    assert stored.platform_message_id == "ic:555"
    assert stored.session == f"github:{instance_id}:issue:hx/HX-Email#42"


def test_bad_signature_is_rejected_and_stores_nothing(
    client: tuple[TestClient, Settings, int],
) -> None:
    test_client, settings, instance_id = client
    assert (
        post(test_client, instance_id, issue_comment_payload(instance_id), signature="sha256=dead")
        == 401
    )
    assert (
        read_messages(settings, 1, f"github:{instance_id}:issue:hx/HX-Email#42", "").messages == []
    )


def test_missing_signature_is_rejected(client: tuple[TestClient, Settings, int]) -> None:
    test_client, _settings, instance_id = client
    assert post(test_client, instance_id, issue_comment_payload(instance_id), signature="") == 401


def test_duplicate_delivery_stores_one_row(client: tuple[TestClient, Settings, int]) -> None:
    test_client, settings, instance_id = client
    payload = issue_comment_payload(instance_id)
    assert post(test_client, instance_id, payload, delivery="d-dup") == 202
    assert post(test_client, instance_id, payload, delivery="d-dup") == 200
    messages = wait_for_messages(settings, 1, f"github:{instance_id}:issue:hx/HX-Email#42")
    assert len(messages) == 1


def test_unknown_instance_is_404(client: tuple[TestClient, Settings, int]) -> None:
    test_client, _settings, _instance_id = client
    assert post(test_client, 9999, issue_comment_payload(9999)) == 404


def test_ping_is_ok_and_unhandled_event_is_204(client: tuple[TestClient, Settings, int]) -> None:
    test_client, _settings, instance_id = client
    ping = {"zen": "Keep it logically awesome."}
    assert post(test_client, instance_id, ping, **{"X-GitHub-Event": "ping"}) == 200
    assert post(test_client, instance_id, {"ref": "x"}, **{"X-GitHub-Event": "star"}) == 204


def test_cursor_advances_after_ingress(client: tuple[TestClient, Settings, int]) -> None:
    test_client, settings, instance_id = client
    before: str = latest_cursor(settings, instance_id)
    assert read_messages(settings, 1, f"github:{instance_id}:issue:", before).messages == []
    assert post(test_client, instance_id, issue_comment_payload(instance_id, 901)) == 202
    messages = wait_for_messages(settings, 1, f"github:{instance_id}:issue:", 1)
    after: str = messages[-1].cursor
    assert after != before
    assert read_messages(settings, 1, f"github:{instance_id}:issue:", after).messages == []
