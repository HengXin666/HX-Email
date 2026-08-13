"""In-memory plugin registry with persistent per-user config via system_settings table."""

from __future__ import annotations

import json
import socket
import ssl
from urllib.parse import urljoin, urlsplit

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail.imap.impl.address_guard import resolve_public_host

_PLUGINS: dict[str, dict[str, object]] = {}

PLUGIN_HEALTH_TIMEOUT: float = 10.0
PLUGIN_MAX_REDIRECTS: int = 5

_REDIRECT_CODES: frozenset[int] = frozenset({301, 302, 303, 307, 308})


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


def uninstall_plugin(settings: Settings, name: str, user_id: int) -> bool:
    """Remove a plugin from the registry and clear the caller's own config."""
    if name not in _PLUGINS:
        return False
    del _PLUGINS[name]
    clear_plugin_config(settings, name, user_id)
    return True


def get_plugin_config(settings: Settings, name: str, user_id: int) -> dict[str, object] | None:
    """Get the current user's stored configuration for a plugin."""
    key = f"plugin_config_{user_id}_{name}"
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT value FROM system_settings WHERE key = ?", (key,)
        ).fetchone()
    if row is None:
        return None
    try:
        result: object = json.loads(str(row["value"]))
        if isinstance(result, dict):
            return {str(k): v for k, v in result.items()}
        return {}
    except (json.JSONDecodeError, TypeError):
        return {}


def save_plugin_config(
    settings: Settings, name: str, user_id: int, config: dict[str, object]
) -> None:
    """Save configuration for a plugin, scoped to the current user."""
    key = f"plugin_config_{user_id}_{name}"
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


def clear_plugin_config(settings: Settings, name: str, user_id: int) -> None:
    """Remove the current user's stored configuration for a plugin."""
    key = f"plugin_config_{user_id}_{name}"
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


def open_plugin_socket(scheme: str, host: str, port: int, timeout: float) -> socket.socket:
    """Resolve the plugin host to a pinned public IP and open a socket.

    The hostname is resolved exactly once and the caller connects to the pinned
    IP literal (closing the DNS-rebinding window), while SNI still names the
    original host so certificate validation keeps working.
    """
    pinned_ip: str = resolve_public_host(host)
    raw: socket.socket = socket.create_connection((pinned_ip, port), timeout=timeout)
    if scheme == "https":
        context: ssl.SSLContext = ssl.create_default_context()
        return context.wrap_socket(raw, server_hostname=host)
    return raw


def read_plugin_http_response(sock: socket.socket) -> tuple[str, dict[str, str], str]:
    """Read one HTTP/1.x response; returns (status_line, headers, body)."""
    data: bytes = b""
    while b"\r\n\r\n" not in data:
        chunk: bytes = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    head, _, body = data.partition(b"\r\n\r\n")
    lines: list[bytes] = head.split(b"\r\n")
    status_line: str = lines[0].decode("latin-1") if lines else ""
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if b":" not in line:
            continue
        key, _, value = line.partition(b":")
        headers[key.decode("latin-1").strip().lower()] = value.decode("latin-1").strip()
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        body += chunk
    return status_line, headers, body.decode("utf-8", errors="replace")


def probe_plugin_health(api_url: str) -> dict[str, object]:
    """Probe a plugin's /health endpoint; the response body is never echoed back.

    Every hop — including redirect targets — is validated as public before any
    connection is made, so a plugin ``api_base_url`` cannot be used to reach
    internal hosts or cloud metadata.
    """
    try:
        parsed = urlsplit(api_url)
    except ValueError:
        return {"success": False, "message": "api_base_url 无效"}
    scheme: str = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        return {"success": False, "message": "api_base_url 仅支持 http/https"}
    host: str | None = parsed.hostname
    if not host:
        return {"success": False, "message": "api_base_url 缺少主机名"}
    try:
        port: int = parsed.port or (443 if scheme == "https" else 80)
    except ValueError:
        return {"success": False, "message": "api_base_url 端口无效"}
    path: str = parsed.path or "/"
    redirects: int = 0
    while True:
        try:
            sock: socket.socket = open_plugin_socket(scheme, host, port, PLUGIN_HEALTH_TIMEOUT)
        except ValueError as error:
            return {"success": False, "message": str(error)}
        except OSError as error:
            return {"success": False, "message": f"连接失败: {error}"}
        try:
            health_path: str = path if path.endswith("/health") else f"{path.rstrip('/')}/health"
            request: bytes = (
                f"GET {health_path} HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                "Accept: application/json\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            sock.sendall(request)
            status_line, headers, _body = read_plugin_http_response(sock)
        except OSError as error:
            return {"success": False, "message": f"请求失败: {error}"}
        finally:
            sock.close()
        parts: list[str] = status_line.split(" ", 2)
        if len(parts) < 2 or not parts[1].isdigit():
            return {"success": False, "message": "服务响应无效"}
        code: int = int(parts[1])
        if code not in _REDIRECT_CODES:
            if 200 <= code < 300:
                return {"success": True, "message": f"连接成功 (HTTP {code})", "status_code": code}
            return {"success": False, "message": f"服务返回 HTTP {code}", "status_code": code}
        location: str = headers.get("location", "")
        if not location:
            return {"success": False, "message": f"重定向缺少 Location (HTTP {code})"}
        redirects += 1
        if redirects > PLUGIN_MAX_REDIRECTS:
            return {"success": False, "message": "重定向次数过多"}
        next_url: str = urljoin(f"{scheme}://{host}:{port}{path}", location)
        try:
            parsed = urlsplit(next_url)
        except ValueError:
            return {"success": False, "message": "重定向目标 URL 无效"}
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            return {"success": False, "message": "重定向目标协议不受支持"}
        host = parsed.hostname or ""
        if not host:
            return {"success": False, "message": "重定向目标缺少主机名"}
        try:
            port = parsed.port or (443 if scheme == "https" else 80)
        except ValueError:
            return {"success": False, "message": "重定向目标端口无效"}
        path = parsed.path or "/"


def test_plugin_connection(settings: Settings, name: str, user_id: int) -> dict[str, object]:
    """Test connectivity to a plugin. Returns a status dict without echoing the body."""
    if name not in _PLUGINS:
        return {"success": False, "message": f"Plugin '{name}' not found"}

    config = get_plugin_config(settings, name, user_id)
    if config is None:
        return {"success": False, "message": "Plugin not configured"}

    api_url: str = str(config.get("api_base_url", "")).strip()
    if not api_url:
        return {"success": False, "message": "No api_base_url configured"}

    return probe_plugin_health(api_url)
