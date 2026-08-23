# fmt: off
# ruff: noqa: E501, E701, E702
"""Enhanced account import - provider routing, auto-detect, pool/groups.

Planners (pure: parse + validate + classify each line into add/update/skip),
then ``import_batch.execute_batch_ops`` runs the ops in ONE connection with
chunked commits. The old path called ``find_account`` + ``add_email_account``
per line (2 connections + 2 commits per line: 5000 lines => ~10000 connects +
~10000 fsync commits — minutes on slow disks, no feedback). Progress is
reported via ``on_progress(processed, imported, skipped, failed)`` so the UI
can render a live progress bar instead of an indefinite spinner.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable

from hx_email.config import Settings
from hx_email.database import connect
from hx_email.server.mail.impl.account_import.import_batch import (
    ImportOp,
    execute_batch_ops,
    existing_address_ids,
)
from hx_email.server.mail.impl.account_import.line_parse import (
    _OUTLOOK_ERR,
    ALLOWED_PROVIDERS,
    ImportLine,
    _detect,
    _is_outlook,
    _like_host,
    _sanitize,
    provider_defaults,
)
from hx_email.server.mail.impl.accounts.account_transfer import (
    EMAIL_PATTERN,
    normalize_lines,
    parse_port,
)

ProgressFn = Callable[[int, int, int, int], None]  # (processed, imported, skipped, failed)

# ---- planning (pure: no DB, no I/O) ----

def _plan_outlook(
    lines: list[str], strategy: str, existing: dict[str, int]
) -> tuple[list[ImportOp], int, list[dict[str, object]]]:
    ops: list[ImportOp] = []; skp: int = 0; errors: list[dict[str, object]] = []
    seen: set[str] = set()
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith("#"): continue
        parts = [p.strip() for p in ln.split("----")]
        if len(parts) < 4: errors.append({"error": "need 4-field OAuth"}); continue
        # 第3段是 "custom" 或形似主机名 => 这是 IMAP 行, 不能当 client_id/refresh_token 吞掉
        if parts[2].lower() == "custom" or _like_host(parts[2]):
            errors.append({"email": parts[0], "error": "IMAP-format line, not Outlook OAuth (choose provider=custom/auto)"}); continue
        email = _sanitize(parts[0], 320); pwd = _sanitize(parts[1], 500)
        cid = _sanitize(parts[2], 200); rtk = _sanitize("----".join(parts[3:]), 4096)
        if not email or not cid or not rtk: errors.append({"email": email, "error": "cid/rtk required"}); continue
        if not EMAIL_PATTERN.match(email): errors.append({"email": email, "error": "invalid email"}); continue
        if email in existing or email in seen:
            if strategy == "skip": skp += 1; continue
            ops.append(ImportOp("update", "outlook", email, pwd, "", None, cid, rtk)); continue
        seen.add(email)
        ops.append(ImportOp("add", "outlook", email, pwd, "", None, cid, rtk))
    return ops, skp, errors


def _plan_imap(
    lines: list[str], provider: str, strategy: str, ch: str, cp: int, existing: dict[str, int]
) -> tuple[list[ImportOp], int, list[dict[str, object]]]:
    cfg = provider_defaults(provider); dh = str(cfg.get("imap_host", ""))
    _dp: object = cfg.get("imap_port", 993); dp: int = _dp if isinstance(_dp, int) else 993
    ops: list[ImportOp] = []; skp: int = 0; errors: list[dict[str, object]] = []
    seen: set[str] = set()
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith("#"): continue
        parts = [p.strip() for p in ln.split("----")]
        if len(parts) < 2: errors.append({"error": "need email----password"}); continue
        email = _sanitize(parts[0], 320); pwd = _sanitize(parts[1], 500)
        if not email or not pwd: errors.append({"email": email, "error": "email/password required"}); continue
        if not EMAIL_PATTERN.match(email): errors.append({"email": email, "error": "invalid email"}); continue
        host, port = dh, dp
        if provider == "custom":
            if len(parts) >= 5 and parts[2].lower() == "custom":
                host = parts[3]; pv = parse_port(parts[4]) if parts[4] else None
                if pv is None: errors.append({"email": email, "error": "invalid port"}); continue
                port = pv
            elif len(parts) >= 4 and _like_host(parts[2]):
                host = parts[2]; pv = parse_port(parts[3]) if parts[3] else None
                if pv is None: errors.append({"email": email, "error": "invalid port"}); continue
                port = pv
            else: host, port = ch, cp
            if not host: errors.append({"email": email, "error": "IMAP host required"}); continue
        elif len(parts) >= 3:
            lp: str = parts[2].strip().lower()
            if lp and lp != provider: errors.append({"email": email, "error": f"provider mismatch: {provider}!={lp}"}); continue
        if _is_outlook(email, host, provider): errors.append({"email": email, "error": _OUTLOOK_ERR}); continue
        if email in existing or email in seen:
            if strategy == "skip": skp += 1; continue
            ops.append(ImportOp("update", provider, email, pwd, host, port, "", "")); continue
        seen.add(email)
        ops.append(ImportOp("add", provider, email, pwd, host, port, "", ""))
    return ops, skp, errors


def _plan_auto(
    lines: list[str], strategy: str, fb_host: str, fb_port: int, existing: dict[str, int]
) -> tuple[list[ImportOp], int, list[dict[str, object]], dict[str, dict[str, int]]]:
    ops: list[ImportOp] = []; skp: int = 0; errors: list[dict[str, object]] = []
    seen: set[str] = set(); bp: dict[str, dict[str, int]] = {}; tmc: int = 0
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith("#"): continue
        r: ImportLine = _detect(ln, fb_host, fb_port)
        if r.line_type == "error": errors.append({"email": "", "error": r.error or "unknown"}); continue
        email = r.address; prov = r.provider
        if not email or not EMAIL_PATTERN.match(email): errors.append({"email": email, "error": "invalid email"}); continue
        bp.setdefault(prov, {"imported": 0, "skipped": 0, "failed": 0})
        if r.line_type == "temp_mail":
            if tmc >= 20: bp[prov]["failed"] += 1; errors.append({"email": email, "error": "temp mail limit 20"}); continue
            if email in existing or email in seen: skp += 1; bp[prov]["skipped"] += 1; continue
            seen.add(email); tmc += 1
            ops.append(ImportOp("add", prov, email, "", "", None, "", "")); continue
        if email in existing or email in seen:
            if strategy == "skip": skp += 1; bp[prov]["skipped"] += 1; continue
            if r.line_type == "outlook":
                ops.append(ImportOp("update", "outlook", email, r.password, "", None, r.client_id, r.refresh_token))
            else: ops.append(ImportOp("update", prov, email, r.password, r.imap_host, r.imap_port, "", ""))
            continue
        seen.add(email)
        if r.line_type == "outlook":
            ops.append(ImportOp("add", "outlook", email, r.password, "", None, r.client_id, r.refresh_token))
        else: ops.append(ImportOp("add", prov, email, r.password, r.imap_host, r.imap_port, "", ""))
    return ops, skp, errors, bp


# ---- import entry points (single connection per import call) ----

def _import_outlook(
    connection: sqlite3.Connection, settings: Settings, user_id: int, lines: list[str], strategy: str,
    group_id: int | None, existing: dict[str, int], on_progress: ProgressFn | None,
) -> dict[str, object]:
    ops, skp, errors = _plan_outlook(lines, strategy, existing)
    base_failed: int = len(errors)
    def cb(processed: int, imported: int, failed: int) -> None:
        if on_progress is not None: on_progress(skp + base_failed + processed, imported, skp, base_failed + failed)
    imp, _ = execute_batch_ops(connection, settings, user_id, ops, existing=existing, group_id=group_id, errors=errors, on_progress=cb)
    return {"imported": imp, "skipped": skp, "failed": len(errors), "errors": errors[:50], "errors_total": len(errors), "duplicate_strategy": strategy}


def _import_imap(
    connection: sqlite3.Connection, settings: Settings, user_id: int, lines: list[str], provider: str, strategy: str,
    ch: str, cp: int, group_id: int | None, existing: dict[str, int], on_progress: ProgressFn | None,
) -> dict[str, object]:
    ops, skp, errors = _plan_imap(lines, provider, strategy, ch, cp, existing)
    base_failed: int = len(errors)
    def cb(processed: int, imported: int, failed: int) -> None:
        if on_progress is not None: on_progress(skp + base_failed + processed, imported, skp, base_failed + failed)
    imp, _ = execute_batch_ops(connection, settings, user_id, ops, existing=existing, group_id=group_id, errors=errors, on_progress=cb)
    return {"imported": imp, "skipped": skp, "failed": len(errors), "errors": errors[:50], "errors_total": len(errors), "duplicate_strategy": strategy}


def _import_auto(
    connection: sqlite3.Connection, settings: Settings, user_id: int, lines: list[str], strategy: str,
    fb_host: str, fb_port: int, group_id: int | None, existing: dict[str, int],
    on_progress: ProgressFn | None,
) -> dict[str, object]:
    ops, skp, errors, bp = _plan_auto(lines, strategy, fb_host, fb_port, existing)
    base_failed: int = len(errors)
    def cb(processed: int, imported: int, failed: int) -> None:
        if on_progress is not None: on_progress(skp + base_failed + processed, imported, skp, base_failed + failed)
    imp, _ = execute_batch_ops(connection, settings, user_id, ops, existing=existing, group_id=group_id, errors=errors, by_provider=bp, on_progress=cb)
    return {"imported": imp, "skipped": skp, "failed": len(errors), "by_provider": bp, "errors": errors[:50], "errors_total": len(errors), "duplicate_strategy": strategy, "mode": "auto"}


# ---- public API ----

def import_accounts_with_provider(
    settings: Settings, user_id: int, text: str, *,
    provider: str = "outlook", group_id: int | None = None, add_to_pool: bool = False,
    duplicate_strategy: str = "skip", custom_imap_host: str = "", custom_imap_port: int = 993,
    on_progress: ProgressFn | None = None,
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
    connection = connect(settings)
    try:
        connection.execute("PRAGMA synchronous=NORMAL")
        existing: dict[str, int] = existing_address_ids(connection, user_id)
        if provider == "auto": return _import_auto(connection, settings, user_id, lines, strategy, custom_imap_host, custom_imap_port, group_id, existing, on_progress)
        if provider == "outlook": return _import_outlook(connection, settings, user_id, lines, strategy, group_id, existing, on_progress)
        return _import_imap(connection, settings, user_id, lines, provider, strategy, custom_imap_host, custom_imap_port, group_id, existing, on_progress)
    finally:
        connection.close()
