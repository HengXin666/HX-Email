"""Row conversion helpers for messaging persistence."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from hx_email.config import Settings
from hx_email.security import decrypt_secret
from hx_email.server.messaging.types import MessagingInstance


def row_to_instance(row: sqlite3.Row, settings: Settings) -> MessagingInstance:
    encrypted: str = str(row["config_encrypted"] or "")
    stored: str = decrypt_secret(settings, encrypted) if encrypted else "{}"
    try:
        raw: Any = json.loads(stored)
        config: dict[str, str] = (
            {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
        )
    except json.JSONDecodeError:
        config = {}
    return MessagingInstance(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        kind=str(row["kind"]),
        name=str(row["name"]),
        status=str(row["status"]),
        config=config,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def safe_json(raw: str) -> dict[str, object]:
    try:
        parsed: Any = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}
