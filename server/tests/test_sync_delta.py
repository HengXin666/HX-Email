"""Incremental sync tests: WAL capture, delta build/apply, full-baseline cadence.

These cover the PG-style design added for 20260823: business writes are
captured into sync_changelog by triggers, regular rounds exchange only the
delta package (build_delta_package/apply_delta_package), and a full snapshot
is taken only when the full-sync watermark is due.
"""

from __future__ import annotations

from pathlib import Path

from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.sync.delta import (
    apply_delta_package,
    build_delta_package,
    build_delta_rows,
)
from hx_email.server.sync.impl.merge import max_changelog_seq
from hx_email.server.sync.service import run_sync
from hx_email.server.sync.watermark import (
    SyncWatermark,
    full_sync_due,
    load_watermark,
)


def _settings(root: Path, name: str) -> Settings:
    return Settings(
        data_dir=root / name,
        admin_username="admin",
        admin_password="admin-password",
        sync_url="http://master.example.com",
        sync_token="secret-token",
    )


def _insert_group(settings: Settings, name: str, color: str) -> None:
    migrate(settings)
    with connect(settings) as connection:
        connection.execute(
            "INSERT INTO groups (user_id, name, color) VALUES (1, ?, ?)",
            (name, color),
        )


def test_business_write_is_captured_into_changelog(tmp_path: Path) -> None:
    settings: Settings = _settings(tmp_path, "node")
    _insert_group(settings, "work", "#ff0000")
    with connect(settings) as connection:
        rows = connection.execute("SELECT table_name, row_id, op FROM sync_changelog").fetchall()
    group_rows = [row for row in rows if row["table_name"] == "groups"]
    assert len(group_rows) == 1
    assert group_rows[0]["op"] == "insert"
    # 初始种子数据 (admin 用户等) 也按 WAL 捕获, 首次增量即可同步用户。
    assert any(row["table_name"] == "users" for row in rows)


def test_merge_suppress_prevents_changelog_pollution(tmp_path: Path) -> None:
    settings: Settings = _settings(tmp_path, "node")
    migrate(settings)
    with connect(settings) as connection:
        connection.execute("DELETE FROM sync_changelog")
        connection.execute("INSERT OR REPLACE INTO sync_suppress (id, active) VALUES (1, 1)")
        connection.execute(
            "INSERT INTO groups (user_id, name, color) VALUES (1, 'muted', '#000000')"
        )
        connection.execute("UPDATE sync_suppress SET active = 0 WHERE id = 1")
    assert max_changelog_seq(settings) == 0


def test_build_delta_package_contains_changed_rows_and_parents(tmp_path: Path) -> None:
    master: Settings = _settings(tmp_path, "master")
    _insert_group(master, "work", "#ff0000")
    with connect(master) as connection:
        connection.execute(
            "INSERT INTO email_accounts (user_id, provider, primary_address, refresh_token)"
            " VALUES (1, 'gmail', 'delta@example.com', 'refresh-delta')"
        )
    watermark: SyncWatermark = SyncWatermark()
    payload, advanced = build_delta_package(master, watermark)
    assert advanced.last_push_seq == max_changelog_seq(master)
    tables: dict[str, object] = payload["tables"]
    assert len(tables["groups"]) == 1
    assert len(tables["email_accounts"]) == 1
    # 引用闭包: email_accounts 的 user_id=1 应带回 users 行, 供 merge remap。
    assert len(tables["users"]) == 1
    assert tables["users"][0]["id"] == 1


def test_apply_delta_package_merges_rows_into_slave(tmp_path: Path) -> None:
    master: Settings = _settings(tmp_path, "master")
    migrate(master)
    with connect(master) as connection:
        connection.execute("DELETE FROM sync_changelog")
        connection.execute(
            "INSERT INTO groups (user_id, name, color) VALUES (1, 'work', '#ff0000')"
        )
    watermark: SyncWatermark = SyncWatermark()
    payload, _ = build_delta_package(master, watermark)

    slave: Settings = _settings(tmp_path, "slave")
    migrate(slave)
    counts: dict[str, int] = apply_delta_package(slave, payload)
    assert counts.get("groups", 0) >= 1
    assert counts.get("users", 0) >= 1
    with connect(slave) as connection:
        row = connection.execute("SELECT color FROM groups WHERE name = 'work'").fetchone()
    assert row is not None
    assert row["color"] == "#ff0000"


def test_apply_delta_is_idempotent(tmp_path: Path) -> None:
    master: Settings = _settings(tmp_path, "master")
    migrate(master)
    with connect(master) as connection:
        connection.execute("DELETE FROM sync_changelog")
        connection.execute(
            "INSERT INTO groups (user_id, name, color) VALUES (1, 'work', '#ff0000')"
        )
    payload, _ = build_delta_package(master, SyncWatermark())

    slave: Settings = _settings(tmp_path, "slave")
    migrate(slave)
    apply_delta_package(slave, payload)
    apply_delta_package(slave, payload)
    with connect(slave) as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS c FROM groups WHERE name = 'work'"
        ).fetchone()
    assert count["c"] == 1


def test_full_sync_due_defaults_to_true_without_watermark(tmp_path: Path) -> None:
    settings: Settings = _settings(tmp_path, "node")
    migrate(settings)
    watermark: SyncWatermark = load_watermark(settings)
    assert full_sync_due(settings, watermark) is True


def test_full_sync_not_due_after_recent_baseline(tmp_path: Path) -> None:
    settings: Settings = _settings(tmp_path, "node")
    migrate(settings)
    from datetime import UTC, datetime, timedelta

    last_full_at: str = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    watermark: SyncWatermark = SyncWatermark(last_full_at=last_full_at)
    assert full_sync_due(settings, watermark) is False


def test_run_sync_without_sync_config_reports_error(tmp_path: Path) -> None:
    settings: Settings = Settings(data_dir=tmp_path / "lonely")
    report = run_sync(settings)
    assert report.error
    assert "sync_url" in report.error
    assert report.tables == {}


def test_build_delta_respects_watermark_watermark(tmp_path: Path) -> None:
    master: Settings = _settings(tmp_path, "master")
    _insert_group(master, "first", "#111111")
    first_seq: int = max_changelog_seq(master)
    _insert_group(master, "second", "#222222")
    rows: dict[str, dict[int, object]] = build_delta_rows(master, first_seq)
    assert "groups" in rows
    assert len(rows["groups"]) == 1
    group: dict[str, object] = next(iter(rows["groups"].values()))
    assert group["name"] == "second"
