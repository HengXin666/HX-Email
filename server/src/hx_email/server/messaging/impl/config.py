"""Config parsing and generation helpers shared by platform adapters."""

import socket


def config_str(config: dict[str, str], key: str, default: str = "") -> str:
    return config.get(key, default).strip()


def config_float(config: dict[str, str], key: str, default: float) -> float:
    try:
        return float(config.get(key, default))
    except (TypeError, ValueError):
        return default


def pick_free_port() -> int:
    """Bind an ephemeral port and return its number (for engine endpoints)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
