"""Google Search Console HTML-file site verification.

Owners can upload the ``google<hash>.html`` file Google issues for domain
verification through the admin settings UI. The file is stored under the
instance data directory and served back at the exact site-root URL Google
fetches (e.g. ``https://<host>/google18261d952ce2f02c.html``) without auth.
"""

from __future__ import annotations

import re
from pathlib import Path

from hx_email.config import Settings

VERIFICATION_FILE_PATTERN: re.Pattern[str] = re.compile(r"^google[0-9a-z]+\.html$")
_VERIFICATION_MARKER: str = "google-site-verification"
_MAX_FILE_SIZE_BYTES: int = 64 * 1024


def verification_dir(settings: Settings) -> Path:
    return settings.data_dir / "verification"


def validate_verification_file(filename: str, content: bytes) -> None:
    """Raise ValueError unless the file looks like a genuine Google file."""
    if not VERIFICATION_FILE_PATTERN.fullmatch(filename):
        raise ValueError("文件名必须是 Google 提供的 google<hash>.html 格式")
    if not content or len(content) > _MAX_FILE_SIZE_BYTES:
        raise ValueError("验证文件内容为空或超过 64KB 限制")
    text = content.decode("utf-8", errors="replace")
    if _VERIFICATION_MARKER not in text or filename.removesuffix(".html") not in text:
        raise ValueError("文件内容不是有效的 Google 站点验证文件")


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
