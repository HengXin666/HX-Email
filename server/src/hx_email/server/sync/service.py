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
from hx_email.server.sync.impl.client import (
    SyncClientError,
    fetch_snapshot,
    push_snapshot_to_master,
)
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
                report.tables = merge_snapshot(
                    connection,
                    settings,
                    staging_dir / DATABASE_NAME,
                    overwrite=overwrite,
                )
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
    """Run a full sync round: pull the master snapshot, then push local data."""
    report: SyncReport = pull_snapshot(settings)
    push_report: SyncReport = push_snapshot(settings)
    report.push = push_report.to_dict()
    report.finished_at = push_report.finished_at or report.finished_at
    if not report.error and push_report.error:
        report.error = push_report.error
    return report
