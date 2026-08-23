from __future__ import annotations

import hashlib
import io
import json
import shutil
import sqlite3
import zipfile
import zlib
from pathlib import Path, PurePosixPath
from typing import Any, cast

from hx_email.config import Settings
from hx_email.database import migrate

BACKUP_FORMAT: str = "hx-email-instance"
BACKUP_VERSION: int = 1
DATABASE_NAME: str = "hx_email.sqlite3"
MANIFEST_NAME: str = "manifest.json"
MAX_ARCHIVE_BYTES: int = 64 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES: int = 128 * 1024 * 1024
MAX_ARCHIVE_FILES: int = 4096
# 运行时数据目录不进备份/同步: 内容可再生且体积巨大 (NapCat 引擎日志/缓存/会话)。
EXCLUDED_DATA_DIR_NAMES: frozenset[str] = frozenset({"qq-engines"})


class InstanceBackupError(ValueError):
    """Raised when an instance backup cannot be safely restored."""


def snapshot_database(source_path: Path, target_path: Path) -> None:
    with (
        sqlite3.connect(source_path, timeout=30) as source,
        sqlite3.connect(target_path, timeout=30) as target,
    ):
        source.backup(target)


def collect_backup_files(data_dir: Path, database_path: Path) -> list[Path]:
    database_resolved: Path = database_path.resolve()
    excluded_names: frozenset[str] = frozenset(
        {
            database_resolved.name,
            f"{database_resolved.name}-wal",
            f"{database_resolved.name}-shm",
            MANIFEST_NAME,
        }
    )
    return sorted(
        path
        for path in data_dir.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and path.name not in excluded_names
        and path.resolve() != database_resolved
        and (
            not path.relative_to(data_dir).parts
            or path.relative_to(data_dir).parts[0] not in EXCLUDED_DATA_DIR_NAMES
        )
    )


def extract_backup_archive(archive_bytes: bytes, staging_path: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            members: list[zipfile.ZipInfo] = archive.infolist()
            if len(members) > MAX_ARCHIVE_FILES:
                raise InstanceBackupError("Backup archive contains too many files")
            uncompressed_size: int = sum(member.file_size for member in members)
            if uncompressed_size > MAX_UNCOMPRESSED_BYTES:
                raise InstanceBackupError("Backup archive expands beyond the allowed size")
            names: set[str] = set()
            for member in members:
                validate_archive_member(member, names)
                names.add(member.filename)
                destination: Path = staging_path.joinpath(*PurePosixPath(member.filename).parts)
                if member.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(member))
                destination.chmod(0o600 if member.filename == ".hx_email_secret_key" else 0o644)
    except InstanceBackupError:
        raise
    except (
        OSError,
        ValueError,
        RuntimeError,
        EOFError,
        NotImplementedError,
        zipfile.BadZipFile,
        zlib.error,
    ) as error:
        raise InstanceBackupError("Invalid backup archive") from error
    manifest_path: Path = staging_path / MANIFEST_NAME
    try:
        raw_manifest: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise InstanceBackupError("Backup manifest is missing or invalid") from error
    if not isinstance(raw_manifest, dict):
        raise InstanceBackupError("Backup manifest must be an object")
    return cast(dict[str, Any], raw_manifest)


def validate_archive_member(member: zipfile.ZipInfo, names: set[str]) -> None:
    name: str = member.filename
    path: PurePosixPath = PurePosixPath(name)
    mode: int = (member.external_attr >> 16) & 0o170000
    if not name or name in names or "\\" in name or path.is_absolute():
        raise InstanceBackupError("Backup archive contains an unsafe path")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise InstanceBackupError("Backup archive contains an unsafe path")
    if mode == 0o120000:
        raise InstanceBackupError("Backup archive cannot contain symbolic links")


def validate_backup_manifest(settings: Settings, manifest: dict[str, Any]) -> None:
    if manifest.get("format") != BACKUP_FORMAT or manifest.get("version") != BACKUP_VERSION:
        raise InstanceBackupError("Unsupported backup format")
    if manifest.get("database") != DATABASE_NAME:
        raise InstanceBackupError("Backup database is missing")
    secret_mode: object = manifest.get("secret_mode")
    target_mode: str = "environment" if settings.secret_key.strip() else "data_dir"
    if secret_mode != target_mode:
        raise InstanceBackupError("Backup secret mode does not match this deployment")
    if target_mode == "environment":
        expected: str = hashlib.sha256(settings.secret_key.encode()).hexdigest()
        if manifest.get("secret_fingerprint") != expected:
            raise InstanceBackupError("HX_EMAIL_SECRET_KEY does not match the backup")


def validate_backup_database(settings: Settings, staging_path: Path) -> None:
    database_path: Path = staging_path / DATABASE_NAME
    if not database_path.is_file():
        raise InstanceBackupError("Backup does not contain a database")
    if not settings.secret_key.strip() and not (staging_path / ".hx_email_secret_key").is_file():
        raise InstanceBackupError("Backup secret key is missing")
    try:
        with sqlite3.connect(database_path) as connection:
            result: sqlite3.Row | tuple[object, ...] | None = connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()
            admin_row: sqlite3.Row | tuple[object, ...] | None = connection.execute(
                "SELECT username FROM users WHERE is_admin = 1 ORDER BY id LIMIT 1"
            ).fetchone()
        if result is None or str(result[0]).lower() != "ok":
            raise InstanceBackupError("Backup database failed integrity check")
        if admin_row is None:
            raise InstanceBackupError("Backup database does not contain an administrator")
        staged_settings: Settings = Settings(
            data_dir=staging_path,
            admin_username=str(admin_row[0]),
            admin_password=settings.admin_password,
            secret_key=settings.secret_key,
        )
        migrate(staged_settings)
    except InstanceBackupError:
        raise
    except (OSError, sqlite3.Error) as error:
        raise InstanceBackupError("Backup database is invalid") from error


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
