"""Raw payload storage and timestamp helpers for stored envelopes (spec 3.1, 10.3)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

RAW_INLINE_LIMIT_BYTES: Final[int] = 16 * 1024
RAW_DIR_NAME: Final[str] = "router_raw"
SQLITE_TIME_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"


def iso_utc_from_unix(seconds: int) -> str:
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_utc_from_sqlite(value: str) -> str:
    """``YYYY-MM-DD HH:MM:SS`` (UTC, SQLite default) to ``YYYY-MM-DDTHH:MM:SSZ``."""
    return value.replace(" ", "T", 1) + "Z" if value and not value.endswith("Z") else value


def encode_raw(raw: dict[str, object] | None) -> str:
    if raw is None:
        return ""
    return json.dumps(raw, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def needs_offload(raw_text: str) -> bool:
    """Raw above 16 KB (project threshold, spec 3.1) goes to a file."""
    return len(raw_text.encode("utf-8")) > RAW_INLINE_LIMIT_BYTES


def raw_relative_path(message_id: int, stored_at: datetime) -> str:
    """``router_raw/<yyyy>/<mm>/<dd>/<id>.json`` with the UTC storage date (spec 10.3)."""
    day: datetime = stored_at.astimezone(UTC)
    return f"{RAW_DIR_NAME}/{day:%Y}/{day:%m}/{day:%d}/{message_id}.json"


def write_raw_file(data_dir: Path, relative_path: str, raw_text: str) -> Path:
    target: Path = data_dir / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(raw_text, encoding="utf-8")
    return target


def load_raw(data_dir: Path, raw_json: str, raw_ref: str) -> dict[str, object] | None:
    """Read raw back from the column or the offloaded file; missing file gives None."""
    text: str = raw_json
    if raw_ref:
        path: Path = data_dir / raw_ref
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8")
    if not text:
        return None
    value: object = json.loads(text)
    return cast(dict[str, object], value) if isinstance(value, dict) else None
