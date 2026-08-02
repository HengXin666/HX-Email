from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from hx_email.config import Settings
from hx_email.database import migrate
from hx_email.security import load_secret_key
from hx_email.server.instance_backup.archive import (
    BACKUP_FORMAT,
    BACKUP_VERSION,
    DATABASE_NAME,
    MANIFEST_NAME,
    MAX_ARCHIVE_BYTES,
    InstanceBackupError,
    collect_backup_files,
    extract_backup_archive,
    remove_path,
    snapshot_database,
    validate_backup_database,
    validate_backup_manifest,
)


def create_instance_backup(settings: Settings) -> bytes:
    """Create a portable ZIP snapshot of the configured data directory."""
    if not settings.database_path.exists():
        migrate(settings)
    data_dir: Path = settings.data_dir.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    secret_mode: str = "environment" if settings.secret_key.strip() else "data_dir"
    if secret_mode == "data_dir":
        load_secret_key(settings)
    secret_fingerprint: str = (
        hashlib.sha256(settings.secret_key.encode()).hexdigest()
        if secret_mode == "environment"
        else ""
    )
    manifest: dict[str, object] = {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "database": DATABASE_NAME,
        "created_at": datetime.now(UTC).isoformat(),
        "secret_mode": secret_mode,
        "secret_fingerprint": secret_fingerprint,
    }
    with tempfile.TemporaryDirectory(prefix="hx-email-backup-") as temp_name:
        snapshot_path: Path = Path(temp_name) / DATABASE_NAME
        snapshot_database(settings.database_path, snapshot_path)
        output: io.BytesIO = io.BytesIO()
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST_NAME, json.dumps(manifest, separators=(",", ":")))
            archive.write(snapshot_path, DATABASE_NAME)
            for path in collect_backup_files(data_dir, settings.database_path):
                archive.write(path, path.relative_to(data_dir).as_posix())
        return output.getvalue()


def restore_instance_backup(
    settings: Settings,
    archive_bytes: bytes,
    pause_scheduler: Callable[[], bool] | None = None,
    resume_scheduler: Callable[[bool], None] | None = None,
) -> None:
    """Validate and atomically replace the configured data directory."""
    if not archive_bytes or len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise InstanceBackupError("Backup archive is empty or too large")
    data_dir: Path = settings.data_dir.resolve()
    parent_dir: Path = data_dir.parent
    parent_dir.mkdir(parents=True, exist_ok=True)
    staging_path: Path | None = Path(
        tempfile.mkdtemp(prefix=f".{data_dir.name}.restore-", dir=parent_dir)
    )
    previous_path: Path = parent_dir / f".{data_dir.name}.previous-{uuid4().hex}"
    scheduler_was_running: bool = False
    swapped: bool = False
    try:
        if staging_path is None:
            raise InstanceBackupError("Could not create restore staging directory")
        manifest: dict[str, object] = extract_backup_archive(archive_bytes, staging_path)
        validate_backup_manifest(settings, manifest)
        validate_backup_database(settings, staging_path)
        (staging_path / MANIFEST_NAME).unlink()
        if pause_scheduler is not None:
            scheduler_was_running = pause_scheduler()
        if data_dir.exists() or data_dir.is_symlink():
            os.replace(data_dir, previous_path)
        os.replace(staging_path, data_dir)
        staging_path = None
        swapped = True
        if resume_scheduler is not None:
            resume_scheduler(scheduler_was_running)
            scheduler_was_running = False
        remove_path(previous_path)
    except Exception:
        if swapped:
            remove_path(data_dir)
        if previous_path.exists():
            os.replace(previous_path, data_dir)
        if scheduler_was_running and resume_scheduler is not None:
            resume_scheduler(True)
        raise
    finally:
        if staging_path is not None:
            remove_path(staging_path)
