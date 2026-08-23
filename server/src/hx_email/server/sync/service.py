"""Master-slave sync orchestration: pull master data and push local changes."""

from __future__ import annotations

import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.instance_backup import InstanceBackupError, create_instance_backup
from hx_email.server.instance_backup.archive import (
    DATABASE_NAME,
    extract_backup_archive,
    validate_backup_database,
    validate_backup_manifest,
)
from hx_email.server.sync.delta import (
    apply_delta_package,
    build_delta_package,
)
from hx_email.server.sync.impl.client import (
    SyncClientError,
    fetch_delta,
    fetch_snapshot,
    push_delta_to_master,
    push_snapshot_to_master,
)
from hx_email.server.sync.impl.files import merge_data_files
from hx_email.server.sync.impl.merge import (
    SyncMergeError,
    max_changelog_seq,
    merge_snapshot,
)
from hx_email.server.sync.watermark import (
    SyncWatermark,
    full_sync_due,
    load_watermark,
    save_watermark,
)

MERGE_ERRORS: tuple[type[BaseException], ...] = (
    SyncClientError,
    InstanceBackupError,
    SyncMergeError,
    sqlite3.Error,
    OSError,
    ValueError,
)


@dataclass
class SyncReport:
    started_at: str = ""
    finished_at: str = ""
    error: str = ""
    tables: dict[str, int] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)
    push: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "tables": dict(self.tables),
            "files": dict(self.files),
            "push": dict(self.push),
        }


def apply_snapshot(
    settings: Settings,
    archive_bytes: bytes,
    overwrite: bool = True,
) -> SyncReport:
    """Merge a peer snapshot into the local data directory (no network)."""
    report: SyncReport = SyncReport(started_at=datetime.now(UTC).isoformat())
    try:
        migrate(settings)
        settings.data_dir.resolve().mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="hx-email-sync-") as temp_name:
            staging_dir: Path = Path(temp_name)
            manifest: dict[str, object] = extract_backup_archive(archive_bytes, staging_dir)
            validate_backup_manifest(settings, manifest)
            validate_backup_database(settings, staging_dir)
            report.files = merge_data_files(staging_dir, settings.data_dir.resolve())
            with connect(settings) as connection:
                connection.execute(
                    "INSERT OR REPLACE INTO sync_suppress (id, active) VALUES (1, 1)"
                )
                try:
                    report.tables = merge_snapshot(
                        connection,
                        settings,
                        staging_dir / DATABASE_NAME,
                        overwrite=overwrite,
                    )
                finally:
                    connection.execute("UPDATE sync_suppress SET active = 0 WHERE id = 1")
        report.finished_at = datetime.now(UTC).isoformat()
    except MERGE_ERRORS as error:
        report.finished_at = datetime.now(UTC).isoformat()
        report.error = str(error)
    return report


def pull_snapshot(settings: Settings) -> SyncReport:
    """Fetch the master snapshot over HTTP and apply it locally."""
    try:
        archive_bytes: bytes = fetch_snapshot(settings)
    except SyncClientError as error:
        report: SyncReport = SyncReport(
            started_at=datetime.now(UTC).isoformat(),
            finished_at=datetime.now(UTC).isoformat(),
            error=str(error),
        )
        return report
    return apply_snapshot(settings, archive_bytes)


def push_snapshot(settings: Settings) -> SyncReport:
    """Snapshot local data and push it to the master for a union merge."""
    report: SyncReport = SyncReport(started_at=datetime.now(UTC).isoformat())
    try:
        archive_bytes: bytes = create_instance_backup(settings)
        master_report: dict[str, Any] = push_snapshot_to_master(settings, archive_bytes)
        report.tables = {
            key: int(value)
            for key, value in master_report.get("tables", {}).items()
            if isinstance(value, int)
        }
        report.files = {
            key: str(value)
            for key, value in master_report.get("files", {}).items()
            if isinstance(value, str)
        }
        report.finished_at = datetime.now(UTC).isoformat()
    except MERGE_ERRORS as error:
        report.finished_at = datetime.now(UTC).isoformat()
        report.error = str(error)
    return report


def run_sync(settings: Settings) -> SyncReport:
    """Run one sync round: incremental delta by default, full baseline on schedule.

    PG 风格: 常规轮次只交换自上次水位以来的变更行 (delta), 内存/带宽开销
    与数据量无关; 仅当距上次全量超过 sync_full_interval_seconds 时执行一次
    全量快照合并作为基线纠偏 (处理删除与跨实例漂移)。
    """
    if not settings.sync_url.strip() or not settings.sync_token.strip():
        unconfigured: SyncReport = SyncReport(
            started_at=datetime.now(UTC).isoformat(),
            finished_at=datetime.now(UTC).isoformat(),
            error="Sync is not configured: set sync_url and sync_token in settings",
        )
        return unconfigured
    migrate(settings)
    watermark: SyncWatermark = load_watermark(settings)
    if full_sync_due(settings, watermark):
        report: SyncReport = run_full_sync(settings)
        if not report.error:
            reset_changelog_after_full(settings)
            watermark.last_full_at = datetime.now(UTC).isoformat()
            watermark.last_pull_seq = max_changelog_seq(settings)
            watermark.last_push_seq = watermark.last_pull_seq
            save_watermark(settings, watermark)
        return report
    return run_delta_sync(settings, watermark)


def run_full_sync(settings: Settings) -> SyncReport:
    """Legacy full snapshot round: pull master snapshot, then push local data."""
    report: SyncReport = pull_snapshot(settings)
    push_report: SyncReport = push_snapshot(settings)
    report.push = push_report.to_dict()
    report.finished_at = push_report.finished_at or report.finished_at
    if not report.error and push_report.error:
        report.error = push_report.error
    return report


def run_delta_sync(settings: Settings, watermark: SyncWatermark) -> SyncReport:
    """Incremental round: pull the master change set, then push local changes."""
    report: SyncReport = SyncReport(started_at=datetime.now(UTC).isoformat())
    try:
        master_payload: dict[str, Any] = fetch_delta(settings, watermark.last_pull_seq)
        applied: dict[str, int] = apply_delta_package(settings, master_payload)
        report.tables = applied
        watermark.last_pull_seq = next_pull_seq(master_payload, watermark.last_pull_seq)
        push_payload, advanced = build_delta_package(settings, watermark)
        if any(isinstance(rows, list) and rows for rows in push_payload.get("tables", {}).values()):
            push_response: dict[str, Any] = push_delta_to_master(settings, push_payload)
            report.push = push_response
        watermark.last_push_seq = advanced.last_push_seq
        save_watermark(settings, watermark)
    except MERGE_ERRORS as error:
        report.error = str(error)
    report.finished_at = datetime.now(UTC).isoformat()
    return report


def next_pull_seq(payload: dict[str, Any], fallback: int) -> int:
    """Return the highest changelog seq covered by the master payload."""
    covered: object = payload.get("seq")
    if isinstance(covered, int) and covered > fallback:
        return covered
    return fallback


def reset_changelog_after_full(settings: Settings) -> None:
    """Drop the changelog after a successful full baseline.

    A full snapshot already carries every row, so replaying old WAL entries
    afterwards would be redundant (and could resurrect rows the merge deleted).
    """
    with connect(settings) as connection:
        connection.execute("DELETE FROM sync_changelog")
