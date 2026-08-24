"""20260823 批量刷新随机错峰: 每账号刷新前随机延迟 1..N 秒.

实测根因: 同批秒级连刷, 微软风控引擎把该簇账号一起标为 compromised
(security interrupt for collecting proof), 错峰打散聚类特征.
"""

from pathlib import Path

import pytest
from hx_email.config import Settings
from hx_email.database import migrate
from hx_email.server.mail.impl.refresh_service import _refresh_account_batch


def make_settings(tmp_path: Path) -> Settings:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    return settings


def test_stagger_sleeps_between_accounts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(tmp_path)
    accounts = [
        {
            "id": i,
            "email": f"a{i}@x.com",
            "provider": "outlook",
            "client_id": "c",
            "refresh_token": "r",
        }
        for i in range(4)
    ]
    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", sleeps.append)
    monkeypatch.setattr(
        "hx_email.server.mail.impl.refresh_service.try_refresh_provider_oauth_token",
        lambda *a, **k: {"success": True, "message": "ok", "error_detail": ""},
    )
    monkeypatch.setattr(
        "hx_email.server.mail.impl.refresh_service._insert_refresh_log",
        lambda *a, **k: None,
    )
    events = list(_refresh_account_batch(settings, 1, accounts))
    # 4 账号 -> 3 次错峰, 每次在 1..20 秒范围(默认)
    assert len(sleeps) == 3, f"应有 3 次错峰, 实际 {len(sleeps)}"
    assert all(1.0 <= d <= 20.0 for d in sleeps), sleeps
    # SSE 事件数 = start + 4 progress + complete
    assert len(events) == 6


def test_stagger_disabled_when_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(tmp_path)
    monkeypatch.setattr(
        "hx_email.server.mail.impl.refresh_service.get_setting",
        lambda *a, **k: "0",
    )
    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", sleeps.append)
    monkeypatch.setattr(
        "hx_email.server.mail.impl.refresh_service.try_refresh_provider_oauth_token",
        lambda *a, **k: {"success": True, "message": "ok", "error_detail": ""},
    )
    monkeypatch.setattr(
        "hx_email.server.mail.impl.refresh_service._insert_refresh_log",
        lambda *a, **k: None,
    )
    accounts = [
        {"id": 1, "email": "a@x.com", "provider": "outlook", "client_id": "c", "refresh_token": "r"}
    ]
    list(_refresh_account_batch(settings, 1, accounts))
    assert sleeps == []
