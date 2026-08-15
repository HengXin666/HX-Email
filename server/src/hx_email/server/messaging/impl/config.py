"""Config parsing helpers shared by platform adapters."""


def config_str(config: dict[str, str], key: str, default: str = "") -> str:
    return config.get(key, default).strip()


def config_float(config: dict[str, str], key: str, default: float) -> float:
    try:
        return float(config.get(key, default))
    except (TypeError, ValueError):
        return default
