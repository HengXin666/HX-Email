"""Validation policy for Google Search Console verification files."""

from __future__ import annotations

import re

VERIFICATION_FILE_PATTERN: re.Pattern[str] = re.compile(r"^google[0-9a-z]+\.html$")
_VERIFICATION_MARKER: str = "google-site-verification"
_MAX_FILE_SIZE_BYTES: int = 64 * 1024


def validate_verification_file(filename: str, content: bytes) -> None:
    """Raise ValueError unless the file looks like a genuine Google file."""
    if not VERIFICATION_FILE_PATTERN.fullmatch(filename):
        raise ValueError("文件名必须是 Google 提供的 google<hash>.html 格式")
    if not content or len(content) > _MAX_FILE_SIZE_BYTES:
        raise ValueError("验证文件内容为空或超过 64KB 限制")
    text = content.decode("utf-8", errors="replace")
    if _VERIFICATION_MARKER not in text or filename.removesuffix(".html") not in text:
        raise ValueError("文件内容不是有效的 Google 站点验证文件")
