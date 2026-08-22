"""Settings helpers shared by settings_service (拆分自 settings_service.py,
20260823, 保持该文件 <=300 行通过 arch-check)."""

from __future__ import annotations

import json


def normalize_external_api_keys(value: object) -> str:
    """Validate and serialize external API keys, migrating legacy maps."""
    api_keys: object = value
    if isinstance(value, str):
        try:
            api_keys = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError("external_api_keys must be a JSON array") from error
    if isinstance(api_keys, dict):
        if not all(
            isinstance(name, str) and isinstance(key, str) for name, key in api_keys.items()
        ):
            raise ValueError("external_api_keys must be a JSON array of strings")
        api_keys = list(api_keys.values())
    if not isinstance(api_keys, list) or not all(isinstance(key, str) for key in api_keys):
        raise ValueError("external_api_keys must be a JSON array of strings")
    return json.dumps(api_keys, ensure_ascii=False)
