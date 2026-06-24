"""In-memory plugin registry with persistent config via system_settings table."""

from __future__ import annotations

from hx_email.config import Settings
from hx_email.database import connect

_PLUGINS: dict[str, dict[str, object]] = {}


def list_plugins() -> list[dict[str, object]]:
    """Return all registered plugins with their metadata."""
    return [
        {
            "name": name,
            "source": info.get("source", ""),
            "version": info.get("version", "0.1.0"),
            "installed_at": info.get("installed_at", ""),
            "enabled": info.get("enabled", True),
        }
        for name, info in _PLUGINS.items()
    ]


def get_plugin(name: str) -> dict[str, object] | None:
    """Get a single plugin by name."""
    info = _PLUGINS.get(name)
    if info is None:
        return None
    return {
        "name": name,
        "source": info.get("source", ""),
        "version": info.get("version", "0.1.0"),
        "installed_at": info.get("installed_at", ""),
        "enabled": info.get("enabled", True),
    }


def install_plugin(settings: Settings, source: str, name: str = "") -> dict[str, object]:
    """Install a plugin from a source identifier."""
    import time

    plugin_name = name or f"plugin_{len(_PLUGINS) + 1}"
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _PLUGINS[plugin_name] = {
        "source": source,
        "version": "0.1.0",
        "installed_at": now,
        "enabled": True,
    }
    return {"name": plugin_name, "source": source}


def uninstall_plugin(settings: Settings, name: str) -> bool:
    """Remove a plugin from the registry. Returns True if removed."""
    if name not in _PLUGINS:
        return False
    del _PLUGINS[name]
    clear_plugin_config(settings, name)
    return True


def get_plugin_config(settings: Settings, name: str) -> dict[str, object] | None:
    """Get stored configuration for a plugin."""
    key = f"plugin_config_{name}"
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT value FROM system_settings WHERE key = ?", (key,)
        ).fetchone()
    if row is None:
        return None
    import json

    try:
        result: object = json.loads(str(row["value"]))
        if isinstance(result, dict):
            return {str(k): v for k, v in result.items()}
        return {}
    except (json.JSONDecodeError, TypeError):
        return {}


def save_plugin_config(settings: Settings, name: str, config: dict[str, object]) -> None:
    """Save configuration for a plugin."""
    import json

    key = f"plugin_config_{name}"
    value = json.dumps(config)
    with connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO system_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def clear_plugin_config(settings: Settings, name: str) -> None:
    """Remove stored configuration for a plugin."""
    key = f"plugin_config_{name}"
    with connect(settings) as connection:
        connection.execute("DELETE FROM system_settings WHERE key = ?", (key,))


def get_plugin_config_schema(name: str) -> dict[str, object]:
    """Return JSON Schema for a plugin's configuration."""
    return {
        "type": "object",
        "properties": {
            "api_base_url": {"type": "string", "description": "API base URL"},
            "api_key": {"type": "string", "description": "API key"},
            "domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Allowed domains",
            },
        },
    }


def test_plugin_connection(settings: Settings, name: str) -> dict[str, object]:
    """Test connectivity to a plugin. Returns status dict."""
    if name not in _PLUGINS:
        return {"success": False, "message": f"Plugin '{name}' not found"}

    config = get_plugin_config(settings, name)
    if config is None:
        return {"success": False, "message": "Plugin not configured"}

    api_url = str(config.get("api_base_url", ""))
    if not api_url:
        return {
            "success": False,
            "message": "No api_base_url configured",
        }

    import json
    import urllib.error
    import urllib.request

    try:
        req = urllib.request.Request(
            f"{api_url.rstrip('/')}/health",
            headers={"Accept": "application/json"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body: str = resp.read().decode("utf-8")
            data: dict[str, object] = json.loads(body)
            return {
                "success": True,
                "message": "Connection successful",
                "response": data,
            }
    except urllib.error.URLError as exc:
        return {"success": False, "message": f"Connection failed: {exc.reason}"}
    except Exception as exc:
        return {"success": False, "message": f"Error: {exc}"}
