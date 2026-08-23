"""Pure parsing layer for credential import: provider registry + line detection.

No DB, no I/O — everything here is deterministic string handling so the
planners in ``import_service`` and the batch executor can share it freely.
"""

# fmt: off
# ruff: noqa: E501, E701, E702
from __future__ import annotations

from dataclasses import dataclass

from hx_email.server.mail.impl.accounts.account_transfer import (
    EMAIL_PATTERN,
    parse_port,
)

# ---- provider registry ----

PROVIDER_DEFAULTS: dict[str, dict[str, object]] = {
    "outlook": {"key": "outlook", "label": "Outlook", "imap_host": "outlook.live.com", "imap_port": 993},
    "gmail": {"key": "gmail", "label": "Gmail", "imap_host": "imap.gmail.com", "imap_port": 993},
    "qq": {"key": "qq", "label": "QQ", "imap_host": "imap.qq.com", "imap_port": 993},
    "163": {"key": "163", "label": "163", "imap_host": "imap.163.com", "imap_port": 993},
    "126": {"key": "126", "label": "126", "imap_host": "imap.126.com", "imap_port": 993},
    "yahoo": {"key": "yahoo", "label": "Yahoo", "imap_host": "imap.mail.yahoo.com", "imap_port": 993},
    "aliyun": {"key": "aliyun", "label": "Aliyun", "imap_host": "imap.aliyun.com", "imap_port": 993},
    "custom": {"key": "custom", "label": "Custom IMAP", "imap_host": "", "imap_port": 993},
}

DOMAIN_PROVIDER_MAP: dict[str, str] = {
    "gmail.com": "gmail", "googlemail.com": "gmail", "qq.com": "qq", "foxmail.com": "qq",
    "163.com": "163", "126.com": "126", "outlook.com": "outlook", "hotmail.com": "outlook",
    "live.com": "outlook", "live.cn": "outlook", "yahoo.com": "yahoo",
    "yahoo.co.jp": "yahoo", "yahoo.co.uk": "yahoo", "aliyun.com": "aliyun", "alimail.com": "aliyun",
}

ALLOWED_PROVIDERS: list[str] = [
    "outlook", "gmail", "qq", "163", "126", "yahoo", "aliyun", "custom", "auto",
]

_OUTLOOK_HOSTS: set[str] = {"outlook.live.com", "outlook.office365.com"}
_OUTLOOK_ERR: str = "Outlook IMAP Basic Auth unsupported, use OAuth: email----password----client_id----refresh_token"


def infer_provider(address: str) -> str:
    domain: str = address.rsplit("@", 1)[-1].lower() if "@" in address else ""
    return DOMAIN_PROVIDER_MAP.get(domain, "custom")


def provider_defaults(provider: str) -> dict[str, object]:
    return PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["custom"])


def get_provider_list() -> list[dict[str, object]]:
    order = ["auto", "outlook", "gmail", "qq", "163", "126", "yahoo", "aliyun", "custom"]
    result: list[dict[str, object]] = [
        {"key": "auto", "label": "Auto Detect", "imap_host": "", "imap_port": 993},
    ]
    for key in order[1:]:
        cfg = PROVIDER_DEFAULTS.get(key, {})
        pv: object = cfg.get("imap_port", 993)
        result.append({
            "key": key, "label": str(cfg.get("label", key)),
            "imap_host": str(cfg.get("imap_host", "")),
            "imap_port": pv if isinstance(pv, int) else 993,
        })
    return result


# ---- helpers ----

def _sanitize(value: object, max_len: int = 500) -> str:
    if value is None: return ""
    t: str = str(value).replace("\r", "").replace("\n", "").replace("\t", "").strip()
    if len(t) > max_len: t = t[:max_len]
    return "".join(ch for ch in t if ch.isprintable())


def _is_outlook(email: str, host: str = "", prov: str = "") -> bool:
    inf = infer_provider(email)
    h = (host or "").strip().lower()
    p = (prov or "").strip().lower()
    return inf == "outlook" or p == "outlook" or h in _OUTLOOK_HOSTS


def _like_host(value: str) -> bool:
    t: str = (value or "").strip().lower()
    return bool(t and "." in t and "@" not in t and " " not in t)


# ---- parsed line ----

@dataclass(frozen=True)
class ImportLine:
    line_type: str; provider: str; address: str; password: str
    imap_host: str; imap_port: int | None; client_id: str; refresh_token: str
    error: str | None = None; group_label: str = ""


# ---- auto-detect (FD-00006) ----

def _detect(line: str, fb_host: str = "", fb_port: int = 993) -> ImportLine:
    parts: list[str] = [p.strip() for p in line.split("----")]
    n: int = len(parts)
    def err(msg: str) -> ImportLine: return ImportLine("error", "", "", "", "", None, "", "", error=msg)

    if n >= 5 and parts[2].lower() == "custom":
        if not parts[0] or not parts[1] or not parts[3]: return err("custom 5-field incomplete")
        port: int | None = parse_port(parts[4]) if parts[4] else None
        if port is None: return err("invalid IMAP port")
        return ImportLine("imap", "custom", parts[0], parts[1], parts[3], port, "", "", group_label="Custom IMAP")

    if n == 4:
        if _like_host(parts[2]):
            if not parts[0] or not parts[1]: return err("custom 4-field missing email/password")
            port = parse_port(parts[3]) if parts[3] else None
            if port is None: return err("invalid IMAP port")
            if _is_outlook(parts[0], parts[2]): return err(_OUTLOOK_ERR)
            return ImportLine("imap", "custom", parts[0], parts[1], parts[2], port, "", "", group_label="Custom IMAP")
        cid, rtk = parts[2], "----".join(parts[3:])
        if not parts[0] or not cid or not rtk: return err("Outlook missing client_id/refresh_token")
        return ImportLine("outlook", "outlook", parts[0], parts[1], "", None, cid, rtk, group_label="Outlook")

    if n == 3:
        if not parts[0] or not parts[1]: return err("3-field missing email/password")
        prov: str = parts[2].lower()
        if prov not in PROVIDER_DEFAULTS: return err(f"unknown provider: {prov}")
        if prov == "outlook": return err("Outlook needs 4-field OAuth format")
        cfg = provider_defaults(prov); h = str(cfg.get("imap_host", ""))
        pv: object = cfg.get("imap_port", 993); pn = pv if isinstance(pv, int) else 993
        return ImportLine("imap", prov, parts[0], parts[1], h, pn, "", "", group_label=str(cfg.get("label", prov)))

    if n == 2:
        if not parts[0] or not parts[1]: return err("2-field missing email/password")
        prov = infer_provider(parts[0])
        if prov == "outlook": return err("Outlook needs 4-field OAuth format")
        if prov == "custom":
            if fb_host: return ImportLine("imap", "custom", parts[0], parts[1], fb_host, fb_port, "", "", group_label="Custom IMAP")
            return err("unknown domain, provide fallback IMAP host")
        cfg = provider_defaults(prov); h = str(cfg.get("imap_host", ""))
        pv = cfg.get("imap_port", 993); pn = pv if isinstance(pv, int) else 993
        return ImportLine("imap", prov, parts[0], parts[1], h, pn, "", "", group_label=str(cfg.get("label", prov)))

    if n == 1:
        email: str = parts[0]
        if not email or "@" not in email: return err("unrecognized line")
        if not EMAIL_PATTERN.match(email): return err("invalid email format")
        return ImportLine("temp_mail", "temp_mail", email, "", "", None, "", "", group_label="Temp Mail")

    return err("unrecognized line")
