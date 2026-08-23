"""Bulk credential-import regression tests.

Covers the async job flow and the batch executor: large imports must complete
with correct counts, and — critically for the reported "导入 5000 条很慢 /
一直导入中" bug — the whole import must use a bounded number of DB connections
(one per call, not ~2 per line). Connection count is asserted via a patch, which
is deterministic, unlike wall-clock timing.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate

from tests.import_client import run_import

API = "/api/v1"


def _make_client(tmp_path: Any) -> tuple[TestClient, dict[str, str], Settings]:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    session = client.post(
        f"{API}/auth/login",
        json={"username": "admin", "password": "admin"},
    ).json()
    return client, {"Authorization": f"Bearer {session['access_token']}"}, settings


def _outlook_lines(n: int) -> str:
    return "\n".join(
        f"bulk{i:05d}@outlook.com----pwd{i}----cid{i}----rtk{i}" + "x" * 40 for i in range(n)
    )


def test_bulk_import_uses_bounded_connections(tmp_path) -> None:
    """The perf regression guard: 800 lines must not open ~1600 connections."""
    client, headers, _settings = _make_client(tmp_path)
    conn_count: list[int] = []
    import hx_email.server.mail.impl.accounts.import_service as isvc

    real_connect = isvc.connect

    def counting_connect(*args: object, **kwargs: object) -> Any:
        conn_count.append(1)
        return real_connect(*args, **kwargs)

    import unittest.mock as mock

    with mock.patch.object(isvc, "connect", counting_connect):
        result = run_import(client, headers, {"provider": "outlook", "text": _outlook_lines(800)})

    assert result["status"] == "done"
    assert result["imported"] == 800
    assert len(conn_count) <= 10, f"expected bounded connects, got {len(conn_count)}"


def test_bulk_import_creates_accounts_and_usable_emails(tmp_path) -> None:
    client, headers, _settings = _make_client(tmp_path)
    result = run_import(client, headers, {"provider": "outlook", "text": _outlook_lines(800)})

    assert result["imported"] == 800
    assert result["failed"] == 0
    assert result["skipped"] == 0

    accounts = client.get(f"{API}/email-accounts?page_size=200", headers=headers).json()
    assert accounts["pagination"]["total_count"] == 800
    first = accounts["accounts"][0]
    assert first["provider"] == "outlook"
    assert first["has_refresh_token"] is True

    emails = client.get(f"{API}/usable-emails", headers=headers).json()
    assert len(emails["usable_emails"]) == 800


def test_bulk_import_duplicate_skip_and_overwrite(tmp_path) -> None:
    client, headers, _settings = _make_client(tmp_path)
    text = _outlook_lines(500)

    first = run_import(client, headers, {"provider": "outlook", "text": text})
    assert first["imported"] == 500

    second = run_import(client, headers, {"provider": "outlook", "text": text})
    assert second["imported"] == 0
    assert second["skipped"] == 500

    overwrite = run_import(
        client,
        headers,
        {"provider": "outlook", "text": text, "duplicate_strategy": "overwrite"},
    )
    assert overwrite["imported"] == 500
    assert overwrite["skipped"] == 0


def test_bulk_import_progress_reaches_total(tmp_path) -> None:
    """The job snapshot must report processed == total and imported counts."""
    client, headers, _settings = _make_client(tmp_path)
    created = client.post(
        f"{API}/email-accounts/import",
        json={"provider": "outlook", "text": _outlook_lines(600)},
        headers=headers,
    )
    assert created.status_code == 202
    job_id: str = created.json()["job_id"]
    assert created.json()["total"] == 600

    deadline: float = time.monotonic() + 30
    final: dict[str, object] = {}
    while time.monotonic() < deadline:
        snap = client.get(f"{API}/email-accounts/import/{job_id}", headers=headers).json()
        if snap["status"] == "done":
            final = snap
            break
        time.sleep(0.01)
    assert final["status"] == "done"
    assert final["total"] == 600
    assert final["processed"] == 600
    assert final["imported"] == 600

    missing = client.get(f"{API}/email-accounts/import/nonexistent-job", headers=headers)
    assert missing.status_code == 404


def test_bulk_import_mixed_auto_provider_breakdown(tmp_path) -> None:
    client, headers, _settings = _make_client(tmp_path)
    text = "\n".join(
        [
            "a1@gmail.com----gmail-pass",
            "a2@qq.com----qq-pass----qq",
            "a3@outlook.com----pw----cid3----rtk3",
            *[f"a{i}@gmail.com----p{i}" for i in range(4, 24)],
        ]
    )
    result = run_import(client, headers, {"provider": "auto", "text": text})

    assert result["imported"] == 23
    by_provider: dict[str, dict[str, int]] = result["by_provider"]
    assert by_provider["gmail"]["imported"] == 21
    assert by_provider["qq"]["imported"] == 1
    assert by_provider["outlook"]["imported"] == 1
