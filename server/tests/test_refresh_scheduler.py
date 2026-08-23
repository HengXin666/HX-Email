"""20260823 后台定时随机刷新调度器: 周期刷新全部账号 OAuth token(错峰)."""

from pathlib import Path

import pytest
from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.mail.impl.refresh.scheduler import TokenRefreshScheduler
from hx_email.server.mail.impl.refresh.settings import (
    get_refresh_scheduler_status,
    refresh_schedule_interval_seconds,
)
from hx_email.server.settings_service import set_setting


def make_settings(tmp_path: Path) -> Settings:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    # 调度器经 patrol 并发刷新, 测试禁用错峰以免拖慢
    set_setting(settings, "refresh_stagger_max_seconds", "0")
    return settings


def test_interval_reads_setting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(tmp_path)
    monkeypatch.setattr(
        "hx_email.server.mail.impl.refresh.settings.get_setting",
        lambda *a, **k: "7200",
    )
    assert refresh_schedule_interval_seconds(settings) == 7200
    monkeypatch.setattr(
        "hx_email.server.mail.impl.refresh.settings.get_setting",
        lambda *a, **k: "bad",
    )
    assert refresh_schedule_interval_seconds(settings) == 3600


def test_run_once_refreshes_all_users(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(tmp_path)
    with connect(settings) as connection:
        connection.execute(
            "INSERT INTO email_accounts (id, user_id, primary_address, provider, client_id, "
            "refresh_token, status) VALUES (1, 7, 'a@outlook.com', 'outlook', 'c', 'r', 'active')"
        )
    scheduler = TokenRefreshScheduler(settings, None)
    monkeypatch.setattr(
        "hx_email.server.mail.impl.patrol.patrol_manager.manager.start",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(
        "hx_email.server.mail.impl.patrol.patrol_manager.manager.snapshot",
        lambda *a, **k: type("S", (), {"total": 1})(),
    )
    monkeypatch.setattr(
        "hx_email.server.mail.impl.patrol.patrol_manager.manager.is_running",
        lambda *a, **k: False,
    )
    summary = scheduler.run_once()
    assert summary["total"] == 1
    assert summary["started_users"] == 1
    status = get_refresh_scheduler_status(settings)
    assert status["enabled"] is True
    assert status["stagger_max_seconds"] >= 0
