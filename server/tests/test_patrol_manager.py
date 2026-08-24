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
from hx_email.server.settings_service import set_setting


def make_settings(tmp_path: Path, concurrent_workers: int = 1) -> Settings:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    # 并发刷新时每个 worker 随机错峰, 测试必须禁用错峰以免拖慢;
    # 默认 1 worker 保持串行语义 (暂停/冻结可稳定断言), 并发路径单独测试。
    set_setting(settings, "refresh_stagger_max_seconds", "0")
    set_setting(settings, "refresh_concurrent_workers", str(concurrent_workers))
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


def _slow_refresh(
    settings: Settings,
    provider: str,
    client_id: str,
    refresh_token: str,
    proxy_url: str = "",
    account_id: int | None = None,
) -> dict[str, object]:
    # 慢速刷新 (0.2s/账号): 保证 pause 冻结断言有足够时间窗口
    time.sleep(0.2)
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
        side_effect=_slow_refresh,
    ):
        assert manager.start(settings, 1, "all") is True
        # 重复启动被拒
        assert manager.start(settings, 1, "all") is False

        snapshot = manager.snapshot(1)
        assert snapshot.status in ("running", "starting")
        assert snapshot.total == 4
        assert snapshot.mode == "all"

        # 等至少一个账号完成 (并发 worker 调度有延迟), 保证有 progress 事件
        deadline: float = time.monotonic() + 3.0
        while manager.snapshot(1).current < 1 and time.monotonic() < deadline:
            time.sleep(0.05)

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


def test_account_stats_refresh_rounds_per_run_success_rate(tmp_path: Path) -> None:
    """每次刷新 = 一轮: 按轮次聚合成功/总数/成功率, 而非按天累计."""
    from hx_email.server.mail.impl.refresh.rounds import (
        create_refresh_round,
        finish_refresh_round,
    )
    from hx_email.server.mail.impl.refresh_log_service import insert_refresh_log

    settings = make_settings(tmp_path)
    add_accounts(settings, 1, 3)  # gmail x3 (id 1-3)
    for index in range(2):
        add_email_account(
            settings,
            1,
            "outlook",
            f"ms{index}@outlook.com",
            f"ms{index}",
            imap_host="outlook.live.com",
            imap_port=993,
            client_id="cid",
            refresh_token="rt",
        )  # outlook x2 (id 4-5)
    client = TestClient(create_app(settings))
    session = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin"},
    ).json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    # 两轮刷新: 第一轮 5 个账号 4 成功 1 失败; 第二轮 2 个账号 1 成功 1 失败
    round_1 = create_refresh_round(settings, 1, "group:3")
    for account_id in range(1, 6):
        insert_refresh_log(
            settings,
            account_id,
            f"a{account_id}@example.com",
            "failed" if account_id == 5 else "success",
            "ok",
            "",
            round_id=round_1,
        )
    finish_refresh_round(settings, round_1, 5, 4, 1)
    round_2 = create_refresh_round(settings, 1, "all")
    for account_id in (1, 2):
        insert_refresh_log(
            settings,
            account_id,
            f"a{account_id}@example.com",
            "failed" if account_id == 2 else "success",
            "ok",
            "",
            round_id=round_2,
        )
    finish_refresh_round(settings, round_2, 2, 1, 1)

    data = client.get("/api/v1/overview/account-stats?provider=microsoft", headers=headers).json()
    rounds = data["refresh_rounds"]
    # 第 2 轮只刷新了 gmail 账号, 在 outlook 视图下不出现 (无该服务商账号的轮次省略)
    assert [r["round_id"] for r in rounds] == [round_1]
    first = rounds[0]
    assert first["total"] == 2  # outlook 账号在第一轮占 2 个 (id 4,5)
    assert first["success"] == 1
    assert first["failed"] == 1
    assert first["success_rate"] == 50.0

    # 服务商过滤: google 视图只统计 gmail 账号
    gmail_only = client.get(
        "/api/v1/overview/account-stats?provider=google", headers=headers
    ).json()["refresh_rounds"]
    assert [r["round_id"] for r in gmail_only] == [round_1, round_2]  # 按时间升序
    assert gmail_only[0]["total"] == 3  # gmail 在第一轮占 3 个
    assert gmail_only[0]["failed"] == 0
    assert gmail_only[0]["success_rate"] == 100.0
    assert gmail_only[1]["total"] == 2
    assert gmail_only[1]["success"] == 1
    assert gmail_only[1]["failed"] == 1
    assert gmail_only[1]["success_rate"] == 50.0


def test_refresh_single_account_writes_round(tmp_path: Path) -> None:
    """单账号刷新也记一轮 (round_id 落库, 轮次表写入成败)."""
    from hx_email.database import connect
    from hx_email.server.mail.impl.refresh.single import refresh_single_account

    settings = make_settings(tmp_path)
    add_accounts(settings, 1, 1)
    with connect(settings) as connection:
        connection.execute("UPDATE email_accounts SET status = 'inactive' WHERE id = 1")
    result = refresh_single_account(settings, 1, 1, object())  # type: ignore[arg-type]
    assert result["success"] is False
    with connect(settings) as connection:
        log = connection.execute(
            "SELECT round_id FROM refresh_logs WHERE account_id = 1"
        ).fetchone()
        round_row = connection.execute(
            "SELECT total, success, failed FROM refresh_rounds WHERE id = ?",
            (log["round_id"],),
        ).fetchone()
    assert round_row["total"] == 1
    assert round_row["failed"] == 1


def test_classify_refresh_error_distinguishes_microsoft_codes() -> None:
    from hx_email.server.mail.impl.refresh_log_service import classify_refresh_error

    # 微软: 令牌失效
    category, _label = classify_refresh_error(
        "outlook",
        '{"error":"invalid_grant","error_description":"AADSTS700082: refresh token expired"}',
    )
    assert category == "token_expired"
    # 微软: 应用配置错误 (client secret)
    category, _label = classify_refresh_error(
        "outlook", "AADSTS7000215: Invalid client secret is provided"
    )
    assert category == "app_config"
    # 微软: 账号被禁用
    category, _label = classify_refresh_error("outlook", "AADSTS50057: User account is disabled")
    assert category == "account_access"
    # 网络
    category, _label = classify_refresh_error(
        "outlook", "HTTPSConnectionPool(host='login.microsoftonline.com')"
    )
    assert category == "network"
    # 谷歌: 令牌失效
    category, _label = classify_refresh_error(
        "gmail", "invalid_grant: Token has been expired or revoked"
    )
    assert category == "token_expired"
    # 兜底
    category, _label = classify_refresh_error("outlook", "something unexpected")
    assert category == "other"


def test_account_stats_includes_groups_and_error_categories(tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta

    from hx_email.server.workspace.groups import create_group

    settings = make_settings(tmp_path)
    group = create_group(settings, 1, "微软号", "#3fb950")
    for index in range(3):
        add_email_account(
            settings,
            1,
            "outlook",
            f"ms{index}@outlook.com",
            f"ms{index}",
            imap_host="outlook.office365.com",
            imap_port=993,
            client_id="cid",
            refresh_token="rt",
        )
    add_email_account(
        settings,
        1,
        "gmail",
        "g@gmail.com",
        "g",
        imap_host="imap.gmail.com",
        imap_port=993,
        client_id="gcid",
        refresh_token="grt",
    )
    client = TestClient(create_app(settings))
    session = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin"},
    ).json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    with connect(settings) as connection:
        connection.execute(
            "UPDATE email_accounts SET group_id = ?, refresh_failed_at = ? WHERE id IN"
            " (SELECT id FROM email_accounts WHERE user_id = 1 ORDER BY id LIMIT 2)",
            (
                group.id,
                (datetime.now(UTC) - timedelta(hours=1))
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
            ),
        )
        # 两条失败日志: 微软令牌过期 + 应用配置错误
        account_ids = [
            row["id"]
            for row in connection.execute(
                "SELECT id FROM email_accounts WHERE user_id = 1 ORDER BY id LIMIT 2"
            ).fetchall()
        ]
        connection.execute(
            "INSERT INTO refresh_logs (account_id, email, status, message,"
            " error_detail, completed_at)"
            " VALUES (?, ?, 'failed', 'x', 'AADSTS700082: refresh token expired', ?)",
            (
                account_ids[0],
                "a@x.com",
                (datetime.now(UTC) - timedelta(hours=2))
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
            ),
        )
        connection.execute(
            "INSERT INTO refresh_logs (account_id, email, status, message,"
            " error_detail, completed_at)"
            " VALUES (?, ?, 'failed', 'x', 'AADSTS7000215: invalid client secret', ?)",
            (
                account_ids[1],
                "b@x.com",
                (datetime.now(UTC) - timedelta(hours=3))
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
            ),
        )
        # 同一账号再失败一次: 应按账号去重, 错误分类计数仍为 1
        connection.execute(
            "INSERT INTO refresh_logs (account_id, email, status, message,"
            " error_detail, completed_at)"
            " VALUES (?, ?, 'failed', 'x', 'AADSTS700082: refresh token expired again', ?)",
            (
                account_ids[0],
                "a@x.com",
                (datetime.now(UTC) - timedelta(hours=1))
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
            ),
        )

    data = client.get("/api/v1/overview/account-stats", headers=headers).json()

    # 仅统计有 token 的 OAuth 账号
    assert data["total"] == 4
    assert data["oauth"] == 4
    assert data["valid"] + data["invalid"] + data["unknown"] == 4
    # 分组拆分: 空分组不输出
    assert len(data["by_group"]) == 1
    assert data["by_group"][0]["name"] == "微软号"
    assert data["by_group"][0]["total"] == 2
    assert data["ungrouped"]["total"] == 2
    # 错误码分类: 令牌失效 + 应用配置 (重复失败日志按账号去重)
    categories = {(c["category"], c["label"]) for c in data["error_categories"]}
    assert ("token_expired", "令牌失效/过期") in categories
    assert ("app_config", "应用配置错误") in categories
    token_expired_count = next(
        c["count"] for c in data["error_categories"] if c["category"] == "token_expired"
    )
    assert token_expired_count == 1

    # provider 筛选: outlook=3, gmail=1
    outlook = client.get(
        "/api/v1/overview/account-stats", params={"provider": "microsoft"}, headers=headers
    ).json()
    assert outlook["total"] == 3
    assert outlook["microsoft"] == 3
    gmail_only = client.get(
        "/api/v1/overview/account-stats", params={"provider": "google"}, headers=headers
    ).json()
    assert gmail_only["total"] == 1
    assert gmail_only["google"] == 1


def test_patrol_parallel_workers_complete_all_and_count(tmp_path: Path) -> None:
    """并发 worker 刷新全部账号并正确计数 (含失败)。"""
    settings = make_settings(tmp_path, concurrent_workers=8)
    add_accounts(settings, 1, 12)

    calls: list[str] = []

    def _mixed_refresh(
        settings: Settings,
        provider: str,
        client_id: str,
        refresh_token: str,
        proxy_url: str = "",
        account_id: int | None = None,
    ) -> dict[str, object]:
        time.sleep(0.02)
        calls.append(str(account_id))
        # 偶数 id 失败, 验证失败计数
        if account_id is not None and account_id % 2 == 0:
            return {"success": False, "message": "boom"}
        return {"success": True, "message": "ok"}

    with patch(
        "hx_email.server.mail.impl.patrol.patrol_manager.try_refresh_provider_oauth_token",
        side_effect=_mixed_refresh,
    ):
        assert manager.start(settings, 1, "all") is True
        _wait_terminal(1)
        snapshot = manager.snapshot(1)
        assert snapshot.status == "done"
        assert snapshot.current == 12
        assert snapshot.success + snapshot.failed == 12
        assert snapshot.failed == 6
        assert snapshot.success == 6
        assert len(calls) == 12
