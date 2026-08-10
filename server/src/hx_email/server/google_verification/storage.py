"""Filesystem storage for Google site-verification files."""

from __future__ import annotations

from pathlib import Path

from hx_email.config import Settings
from hx_email.server.google_verification.policy import (
    VERIFICATION_FILE_PATTERN,
    validate_verification_file,
)


def verification_dir(settings: Settings) -> Path:
    return settings.data_dir / "verification"


def save_verification_file(settings: Settings, filename: str, content: bytes) -> Path:
    validate_verification_file(filename, content)
    directory = verification_dir(settings)
    directory.mkdir(parents=True, exist_ok=True)
    # Keep a single active verification file so stale tokens never linger.
    for existing in directory.glob("google*.html"):
        existing.unlink(missing_ok=True)
    target = directory / filename
    target.write_bytes(content)
    return target


def list_verification_files(settings: Settings) -> list[str]:
    directory = verification_dir(settings)
    if not directory.is_dir():
        return []
    return sorted(path.name for path in directory.glob("google*.html") if path.is_file())


def delete_verification_file(settings: Settings, filename: str) -> bool:
    if not VERIFICATION_FILE_PATTERN.fullmatch(filename):
        return False
    target = verification_dir(settings) / filename
    if not target.is_file():
        return False
    target.unlink()
    return True


def resolve_verification_file(settings: Settings, filename: str) -> Path | None:
    if not VERIFICATION_FILE_PATTERN.fullmatch(filename):
        return None
    target = verification_dir(settings) / filename
    return target if target.is_file() else None
