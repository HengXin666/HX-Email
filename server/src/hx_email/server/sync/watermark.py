"""Sync watermarks: per-instance progress pointers for the delta WAL.

Each instance records where it stands in the replication stream:
  - last_pull_seq: highest changelog seq applied from the master
  - last_push_seq: highest local changelog seq already pushed
  - last_full_at:  timestamp of the last full baseline (for periodic resync)

PG 的 replication slot 水位对应物: 增量同步以这两个 seq 为游标, 全量基线
以 last_full_at 决定何时重新做一次快照合并纠偏。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from hx_email.config import Settings
from hx_email.database import connect

FULL_SYNC_DEFAULT_SECONDS: int = 86_400  # 24h
WATERMARK_TABLE: str = "sync_watermark"


@dataclass
class SyncWatermark:
    last_pull_seq: int = 0
    last_push_seq: int = 0
    last_full_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "last_pull_seq": self.last_pull_seq,
            "last_push_seq": self.last_push_seq,
            "last_full_at": self.last_full_at,
        }


def ensure_watermark_table(settings: Settings) -> None:
    with connect(settings) as connection:
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {WATERMARK_TABLE} (
                key TEXT PRIMARY KEY, value TEXT NOT NULL
            )
            """
        )


def load_watermark(settings: Settings) -> SyncWatermark:
    ensure_watermark_table(settings)
    watermark: SyncWatermark = SyncWatermark()
    with connect(settings) as connection:
        rows = connection.execute(f"SELECT key, value FROM {WATERMARK_TABLE}").fetchall()
    values: dict[str, str] = {str(row["key"]): str(row["value"]) for row in rows}
    watermark.last_pull_seq = int(values.get("last_pull_seq", "0") or "0")
    watermark.last_push_seq = int(values.get("last_push_seq", "0") or "0")
    watermark.last_full_at = values.get("last_full_at", "")
    return watermark


def save_watermark(settings: Settings, watermark: SyncWatermark) -> None:
    ensure_watermark_table(settings)
    with connect(settings) as connection:
        connection.execute(
            f"INSERT OR REPLACE INTO {WATERMARK_TABLE} (key, value) VALUES ('last_pull_seq', ?)",
            (str(watermark.last_pull_seq),),
        )
        connection.execute(
            f"INSERT OR REPLACE INTO {WATERMARK_TABLE} (key, value) VALUES ('last_push_seq', ?)",
            (str(watermark.last_push_seq),),
        )
        connection.execute(
            f"INSERT OR REPLACE INTO {WATERMARK_TABLE} (key, value) VALUES ('last_full_at', ?)",
            (watermark.last_full_at,),
        )


def full_sync_due(settings: Settings, watermark: SyncWatermark) -> bool:
    """True when the last full baseline is older than the configured interval."""
    if not watermark.last_full_at:
        return True
    try:
        last: datetime = datetime.fromisoformat(watermark.last_full_at)
    except ValueError:
        return True
    interval: int = getattr(settings, "sync_full_interval_seconds", FULL_SYNC_DEFAULT_SECONDS)
    return (datetime.now(UTC) - last).total_seconds() >= interval
