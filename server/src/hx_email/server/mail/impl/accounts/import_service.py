# fmt: off
# ruff: noqa: E501, E701, E702
"""Enhanced account import - provider routing, auto-detect, pool/groups."""
from __future__ import annotations

from dataclasses import dataclass

from hx_email.config import Settings
from hx_email.server.mail.email_accounts import DuplicateUsableEmailError, add_email_account
from hx_email.server.mail.impl.accounts.account_transfer import (
    EMAIL_PATTERN,
    ParsedAccountLine,
    find_account,
    normalize_lines,
    parse_port,
    update_account_credentials,
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


# ---- import: outlook ----

def _import_outlook(settings: Settings, user_id: int, lines: list[str], strategy: str, group_id: int | None = None) -> dict[str, object]:
    imp, skp, fld = 0, 0, 0
    errors: list[dict[str, object]] = []
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith("#"): continue
        parts = [p.strip() for p in ln.split("----")]
        if len(parts) < 4: fld += 1; errors.append({"error": "need 4-field OAuth"}); continue
        email = _sanitize(parts[0], 320); pwd = _sanitize(parts[1], 500)
        cid = _sanitize(parts[2], 200); rtk = _sanitize("----".join(parts[3:]), 4096)
        if not email or not cid or not rtk: fld += 1; errors.append({"email": email, "error": "cid/rtk required"}); continue
        if not EMAIL_PATTERN.match(email): fld += 1; errors.append({"email": email, "error": "invalid email"}); continue
        existing = find_account(settings, user_id, email)
        if existing is not None:
            if strategy == "skip": skp += 1; continue
            update_account_credentials(settings, user_id, int(existing["id"]), ParsedAccountLine(email, pwd, "outlook", "", None, cid, rtk))
            imp += 1; continue
        try: add_email_account(settings, user_id, "outlook", email, email, "", None, email, pwd, cid, rtk, [], group_id); imp += 1
        except DuplicateUsableEmailError as exc: fld += 1; errors.append({"email": email, "error": str(exc)})
    return {"imported": imp, "skipped": skp, "failed": fld, "errors": errors[:50], "errors_total": len(errors), "duplicate_strategy": strategy}


# ---- import: imap ----

def _import_imap(settings: Settings, user_id: int, lines: list[str], provider: str, strategy: str, ch: str = "", cp: int = 993, group_id: int | None = None) -> dict[str, object]:
    cfg = provider_defaults(provider); dh = str(cfg.get("imap_host", ""))
    _dp: object = cfg.get("imap_port", 993); dp: int = _dp if isinstance(_dp, int) else 993
    imp, skp, fld = 0, 0, 0; errors: list[dict[str, object]] = []
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith("#"): continue
        parts = [p.strip() for p in ln.split("----")]
        if len(parts) < 2: fld += 1; errors.append({"error": "need email----password"}); continue
        email = _sanitize(parts[0], 320); pwd = _sanitize(parts[1], 500)
        if not email or not pwd: fld += 1; errors.append({"email": email, "error": "email/password required"}); continue
        if not EMAIL_PATTERN.match(email): fld += 1; errors.append({"email": email, "error": "invalid email"}); continue
        host, port = dh, dp
        if provider == "custom":
            if len(parts) >= 5 and parts[2].lower() == "custom":
                host = parts[3]; pv = parse_port(parts[4]) if parts[4] else None
                if pv is None: fld += 1; errors.append({"email": email, "error": "invalid port"}); continue
                port = pv
            elif len(parts) >= 4 and _like_host(parts[2]):
                host = parts[2]; pv = parse_port(parts[3]) if parts[3] else None
                if pv is None: fld += 1; errors.append({"email": email, "error": "invalid port"}); continue
                port = pv
            else: host, port = ch, cp
            if not host: fld += 1; errors.append({"email": email, "error": "IMAP host required"}); continue
        elif len(parts) >= 3:
            lp: str = parts[2].strip().lower()
            if lp and lp != provider: fld += 1; errors.append({"email": email, "error": f"provider mismatch: {provider}!={lp}"}); continue
        if _is_outlook(email, host, provider): fld += 1; errors.append({"email": email, "error": _OUTLOOK_ERR}); continue
        existing = find_account(settings, user_id, email)
        if existing is not None:
            if strategy == "skip": skp += 1; continue
            update_account_credentials(settings, user_id, int(existing["id"]), ParsedAccountLine(email, pwd, provider, host, port, "", ""))
            imp += 1; continue
        try: add_email_account(settings, user_id, provider, email, email, host, port, email, pwd, "", "", [], group_id); imp += 1
        except DuplicateUsableEmailError as exc: fld += 1; errors.append({"email": email, "error": str(exc)})
    return {"imported": imp, "skipped": skp, "failed": fld, "errors": errors[:50], "errors_total": len(errors), "duplicate_strategy": strategy}


# ---- import: auto ----

def _import_auto(settings: Settings, user_id: int, lines: list[str], strategy: str, fb_host: str = "", fb_port: int = 993, group_id: int | None = None) -> dict[str, object]:
    imp, skp, fld, tmc = 0, 0, 0, 0; bp: dict[str, dict[str, int]] = {}; errors: list[dict[str, object]] = []
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith("#"): continue
        r: ImportLine = _detect(ln, fb_host, fb_port)
        if r.line_type == "error": fld += 1; errors.append({"email": "", "error": r.error or "unknown"}); continue
        email = r.address; prov = r.provider
        if not email or not EMAIL_PATTERN.match(email): fld += 1; errors.append({"email": email, "error": "invalid email"}); continue
        bp.setdefault(prov, {"imported": 0, "skipped": 0, "failed": 0})
        if r.line_type == "temp_mail":
            if tmc >= 20: fld += 1; bp[prov]["failed"] += 1; errors.append({"email": email, "error": "temp mail limit 20"}); continue
            existing = find_account(settings, user_id, email)
            if existing is not None: skp += 1; bp[prov]["skipped"] += 1; continue
            try: add_email_account(settings, user_id, "temp_mail", email, email, "", None, email, "", "", "", [], group_id); imp += 1; tmc += 1; bp[prov]["imported"] += 1
            except DuplicateUsableEmailError: skp += 1; bp[prov]["skipped"] += 1
            continue
        existing = find_account(settings, user_id, email)
        if existing is not None:
            if strategy == "skip": skp += 1; bp[prov]["skipped"] += 1; continue
            if r.line_type == "outlook":
                update_account_credentials(settings, user_id, int(existing["id"]), ParsedAccountLine(email, r.password, "outlook", "", None, r.client_id, r.refresh_token))
            else: update_account_credentials(settings, user_id, int(existing["id"]), ParsedAccountLine(email, r.password, prov, r.imap_host, r.imap_port, "", ""))
            imp += 1; bp[prov]["imported"] += 1; continue
        try:
            if r.line_type == "outlook": add_email_account(settings, user_id, "outlook", email, email, "", None, email, r.password, r.client_id, r.refresh_token, [], group_id)
            else: add_email_account(settings, user_id, prov, email, email, r.imap_host, r.imap_port, email, r.password, "", "", [], group_id)
            imp += 1; bp[prov]["imported"] += 1
        except DuplicateUsableEmailError as exc: fld += 1; bp[prov]["failed"] += 1; errors.append({"email": email, "error": str(exc)})
    return {"imported": imp, "skipped": skp, "failed": fld, "by_provider": bp, "errors": errors[:50], "errors_total": len(errors), "duplicate_strategy": strategy, "mode": "auto"}


# ---- public API ----

def import_accounts_with_provider(
    settings: Settings, user_id: int, text: str, *,
    provider: str = "outlook", group_id: int | None = None, add_to_pool: bool = False,
    duplicate_strategy: str = "skip", custom_imap_host: str = "", custom_imap_port: int = 993,
) -> dict[str, object]:
    if provider not in ALLOWED_PROVIDERS: provider = "outlook"
    lines: list[str] = normalize_lines(text)
    if provider == "auto":
        merged: list[str] = []
        for ln in lines:
            if merged and "----" not in ln and not ln.startswith("#"): merged[-1] += ln
            else: merged.append(ln)
        lines = merged
    strategy: str = duplicate_strategy if duplicate_strategy in ("skip", "overwrite") else "skip"
    if provider == "auto": return _import_auto(settings, user_id, lines, strategy, custom_imap_host, custom_imap_port, group_id)
    if provider == "outlook": return _import_outlook(settings, user_id, lines, strategy, group_id)
    return _import_imap(settings, user_id, lines, provider, strategy, custom_imap_host, custom_imap_port, group_id)
