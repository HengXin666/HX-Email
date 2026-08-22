"""持久化巡检管理器: 后台线程状态机 (启动/暂停/恢复/终止) 与 HTTP 端点。"""

import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.mail.email_accounts import add_email_account
from hx_email.server.mail.impl.patrol.patrol_manager import manager


def make_settings(tmp_path: Path) -> Settings:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    return settings


def add_accounts(settings: Settings, user_id: int, count: int = 4) -> None:
    for index in range(count):
        add_email_account(
            settings,
            user_id,
            "gmail",
            f"patrol{index}@gmail.com",
            f"patrol{index}",
            imap_host="imap.gmail.com",
            imap_port=993,
            client_id="cid",
            refresh_token="rt",
        )


def _fake_refresh(
    settings: Settings,
    provider: str,
    client_id: str,
    refresh_token: str,
    proxy_url: str = "",
    account_id: int | None = None,
) -> dict[str, object]:
    time.sleep(0.05)
    return {"success": True, "message": "ok"}


def _wait_terminal(user_id: int, timeout: float = 10.0) -> None:
    deadline: float = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = manager.snapshot(user_id)
        if snapshot.status in ("done", "error", "stopped", "idle"):
            return
        time.sleep(0.05)
    raise AssertionError("patrol did not reach terminal state in time")


def test_patrol_manager_runs_in_background_and_supports_pause_resume_stop(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    add_accounts(settings, 1, 4)

    with patch(
        "hx_email.server.mail.impl.patrol.patrol_manager.try_refresh_provider_oauth_token",
        side_effect=_fake_refresh,
    ):
        assert manager.start(settings, 1, "all") is True
        # 重复启动被拒
        assert manager.start(settings, 1, "all") is False

        snapshot = manager.snapshot(1)
        assert snapshot.status in ("running", "starting")
        assert snapshot.total == 4
        assert snapshot.mode == "all"

        # 暂停: 进度冻结
        assert manager.pause(1) is True
        time.sleep(0.2)
        paused = manager.snapshot(1)
        assert paused.status == "paused"
        frozen = paused.current
        time.sleep(0.2)
        assert manager.snapshot(1).current == frozen

        # 恢复后立即终止
        assert manager.resume(1) is True
        assert manager.stop(1) is True
        _wait_terminal(1)
        final = manager.snapshot(1)
        assert final.status == "stopped"
        assert final.success + final.failed <= 4

        # 事件流包含 start/progress/complete, 且带序号可回放
        events = manager.events_since(1, 0)
        types = [str(event.get("type")) for _seq, event in events]
        assert "start" in types
        assert "progress" in types
        assert "complete" in types
        assert events[0][0] == 1  # 序号从 1 开始


def test_patrol_completes_all_accounts_and_counts_results(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    add_accounts(settings, 1, 3)

    with patch(
        "hx_email.server.mail.impl.patrol.patrol_manager.try_refresh_provider_oauth_token",
        side_effect=_fake_refresh,
    ):
        assert manager.start(settings, 1, "all") is True
        _wait_terminal(1)
        snapshot = manager.snapshot(1)
        assert snapshot.status == "done"
        assert snapshot.current == 3
        assert snapshot.success == 3
        assert snapshot.failed == 0


def test_patrol_endpoints_start_status_stream_stop(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    add_accounts(settings, 1, 2)
    client = TestClient(create_app(settings))
    session = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin"},
    ).json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    with patch(
        "hx_email.server.mail.impl.patrol.patrol_manager.try_refresh_provider_oauth_token",
        side_effect=_fake_refresh,
    ):
        started = client.post(
            "/api/v1/email-accounts/patrol/start", json={"mode": "all"}, headers=headers
        )
        assert started.status_code == 200
        assert started.json()["success"] is True

        duplicate = client.post(
            "/api/v1/email-accounts/patrol/start", json={"mode": "all"}, headers=headers
        )
        assert duplicate.status_code == 409

        status = client.get("/api/v1/email-accounts/patrol/status", headers=headers).json()
        assert status["status"] in ("running", "starting", "paused", "stopping")
        assert status["total"] == 2

        # SSE 流: 读取至结束, 应包含 start 与 complete 事件
        with client.stream(
            "GET", "/api/v1/email-accounts/patrol/stream", headers=headers
        ) as stream:
            assert stream.status_code == 200
            content = stream.read()
        assert b"event: start" in content
        assert b"event: complete" in content

        final = client.get("/api/v1/email-accounts/patrol/status", headers=headers).json()
        assert final["status"] == "done"

        # 暂停/恢复/终止接口
        assert manager.start(settings, 1, "all") is True
        assert (
            client.post("/api/v1/email-accounts/patrol/pause", headers=headers).json()["success"]
            is True
        )
        assert (
            client.post("/api/v1/email-accounts/patrol/resume", headers=headers).json()["success"]
            is True
        )
        assert (
            client.post("/api/v1/email-accounts/patrol/stop", headers=headers).json()["success"]
            is True
        )
        _wait_terminal(1)


def test_account_stats_endpoint_aggregates_counts_and_series(tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta

    settings = make_settings(tmp_path)
    add_accounts(settings, 1, 3)
    client = TestClient(create_app(settings))
    session = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin"},
    ).json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    with connect(settings) as connection:
        # 一个 40 天前、一个 5 天前; 40 天前的标记为刷新成功, 5 天前的标记为失败
        connection.execute(
            "UPDATE email_accounts SET created_at = ?, last_refresh_at = ?,"
            " refresh_failed_at = NULL WHERE primary_address = ?",
            (
                (datetime.now(UTC) - timedelta(days=40))
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
                (datetime.now(UTC) - timedelta(days=1))
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
                "patrol0@gmail.com",
            ),
        )
        connection.execute(
            "UPDATE email_accounts SET created_at = ?, refresh_failed_at = ?"
            " WHERE primary_address = ?",
            (
                (datetime.now(UTC) - timedelta(days=5))
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
                (datetime.now(UTC) - timedelta(hours=1))
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
                "patrol1@gmail.com",
            ),
        )

    data = client.get("/api/v1/overview/account-stats", headers=headers).json()

    assert data["total"] == 3
    assert data["oauth"] == 3
    assert data["valid"] == 1
    assert data["invalid"] == 1
    assert data["unknown"] == 1
    assert len(data["age_buckets"]) == 7
    assert data["age_buckets"][3]["valid"] == 1  # 30-60天 桶含 40 天前的账号
    assert len(data["daily_new"]) == 30
    assert len(data["daily_refresh"]) == 30
    assert data["by_provider"][0]["provider"] == "gmail"
