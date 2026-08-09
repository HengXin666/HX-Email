"""Master-slave sync orchestration: pull a snapshot and merge it locally."""

from __future__ import annotations

import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.server.instance_backup.archive import (
    DATABASE_NAME,
    InstanceBackupError,
    extract_backup_archive,
    validate_backup_database,
    validate_backup_manifest,
)
from hx_email.server.sync.impl.client import SyncClientError, fetch_snapshot
from hx_email.server.sync.impl.files import merge_data_files
from hx_email.server.sync.impl.merge import SyncMergeError, merge_snapshot

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

    def to_dict(self) -> dict[str, object]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "tables": dict(self.tables),
            "files": dict(self.files),
        }


def apply_snapshot(settings: Settings, archive_bytes: bytes) -> SyncReport:
    """Merge a master snapshot into the local data directory (no network)."""
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
                report.tables = merge_snapshot(connection, settings, staging_dir / DATABASE_NAME)
        report.finished_at = datetime.now(UTC).isoformat()
    except MERGE_ERRORS as error:
        report.finished_at = datetime.now(UTC).isoformat()
        report.error = str(error)
    return report


def run_sync(settings: Settings) -> SyncReport:
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
