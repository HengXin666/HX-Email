"""Copy data files from an extracted backup with content-hash deduplication."""

from __future__ import annotations

import hashlib
from pathlib import Path

from hx_email.server.instance_backup.archive import (
    DATABASE_NAME,
    EXCLUDED_DATA_DIR_NAMES,
    MANIFEST_NAME,
)

SKIPPED_NAMES: frozenset[str] = frozenset(
    {
        DATABASE_NAME,
        MANIFEST_NAME,
        f"{DATABASE_NAME}-wal",
        f"{DATABASE_NAME}-shm",
    }
)
SECRET_KEY_NAME: str = ".hx_email_secret_key"


def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def merge_data_files(staging_dir: Path, data_dir: Path) -> dict[str, str]:
    """Copy snapshot files into the live data dir; identical files are skipped."""
    result: dict[str, str] = {}
    for path in sorted(staging_dir.rglob("*")):
        if not path.is_file():
            continue
        relative: str = path.relative_to(staging_dir).as_posix()
        if relative in SKIPPED_NAMES:
            continue
        if relative.split("/", 1)[0] in EXCLUDED_DATA_DIR_NAMES:
            continue
        target: Path = data_dir.joinpath(*path.relative_to(staging_dir).parts)
        digest: str = sha256_of_bytes(path.read_bytes())
        if relative == SECRET_KEY_NAME and target.exists():
            result[relative] = "kept"
            continue
        if target.exists() and sha256_of_bytes(target.read_bytes()) == digest:
            result[relative] = "unchanged"
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        target.chmod(0o600 if relative == SECRET_KEY_NAME else 0o644)
        result[relative] = "copied"
    return result
