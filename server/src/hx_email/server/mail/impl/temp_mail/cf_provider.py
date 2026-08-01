"""Cloudflare Worker temp mail provider (cloudflare_temp_email Worker API).

Worker endpoints used:
- POST /admin/new_address  (header x-admin-auth)      -> create mailbox, returns address/jwt/id
- GET  /api/mails          (header Authorization jwt) -> list messages, each with raw MIME
"""

from __future__ import annotations

import email
import email.policy
import json
import re
import secrets
import string
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any

from hx_email.config import Settings
from hx_email.server.mail.temp_mail import (
    MissingTempMailProviderError,
    ProviderMailbox,
    TempMailMessage,
    TempMailMessageLike,
    TempMailProviderError,
)
from hx_email.server.settings_service import get_setting

_TIMEOUT: int = 20

# Cloudflare bot protection (error 1010) rejects the default Python-urllib
# User-Agent signature, so requests must present a browser-like UA.
_BROWSER_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def _http_request(
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
) -> tuple[int, str]:
    data: bytes | None = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise TempMailProviderError(f"CF Worker 网络错误: {exc.reason}") from exc
    except TimeoutError as exc:
        raise TempMailProviderError("CF Worker 请求超时") from exc


def _parse_json_object(body: str) -> dict[str, Any]:
    try:
        data: Any = json.loads(body)
    except ValueError as exc:
        raise TempMailProviderError("CF Worker 返回非 JSON 响应") from exc
    if not isinstance(data, dict):
        raise TempMailProviderError("CF Worker 返回结构异常")
    return data


def _split_address(requested: str | None) -> tuple[str, str]:
    """Split an optional "prefix@domain" request into (prefix, domain)."""
    value: str = (requested or "").strip()
    if not value:
        return "", ""
    if "@" in value:
        name, _, domain = value.partition("@")
        return name.strip(), domain.strip()
    return value, ""


def _extract_jwt(provider_mailbox_id: str) -> str:
    """provider_mailbox_id stores JSON {"id", "jwt"}; legacy rows may hold a bare jwt."""
    try:
        data: Any = json.loads(provider_mailbox_id)
    except ValueError:
        return provider_mailbox_id.strip()
    if isinstance(data, dict):
        return str(data.get("jwt") or "").strip()
    return ""


def _parse_mime(raw: str) -> tuple[str, str, str, str]:
    """Parse a raw MIME message into (subject, from_address, text, html)."""
    message = email.message_from_string(raw, policy=email.policy.default)
    subject: str = str(message.get("Subject") or "")
    from_address: str = str(message.get("From") or "")
    text: str = ""
    html: str = ""
    for part in message.walk():
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        payload: Any = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            continue
        charset: str = part.get_content_charset() or "utf-8"
        try:
            content: str = payload.decode(charset, errors="replace")
        except LookupError:
            content = payload.decode("utf-8", errors="replace")
        content = _decode_json_unicode_escapes(content)
        content_type: str = part.get_content_type()
        if content_type == "text/plain" and not text:
            text = content
        elif content_type == "text/html" and not html:
            html = content
    return subject, from_address, text, html


def _decode_json_unicode_escapes(value: str) -> str:
    """Decode literal JSON Unicode escapes left in stored Worker MIME bodies."""

    def decode_match(match: re.Match[str]) -> str:
        escaped: str = match.group(0)
        try:
            decoded: object = json.loads(f'"{escaped}"')
        except (TypeError, ValueError):
            return escaped
        return decoded if isinstance(decoded, str) else escaped

    pattern: str = (
        r"\\u(?:[dD][89abAB][0-9a-fA-F]{2}\\u[dD][c-fC-F][0-9a-fA-F]{2}" r"|[0-9a-fA-F]{4})"
    )
    return re.sub(pattern, decode_match, value)


def _normalize_message(item: dict[str, Any]) -> TempMailMessage:
    raw_id: Any = item.get("id")
    message_id: str = f"cf_{raw_id}" if raw_id is not None else ""
    raw_mime: str = str(item.get("raw") or "")
    subject, from_address, text, html = _parse_mime(raw_mime) if raw_mime else ("", "", "", "")
    if not from_address:
        from_address = str(item.get("source") or "")
    if not subject:
        subject = str(item.get("subject") or "")
    if not text and not html:
        text = str(item.get("text") or "")
        html = str(item.get("html") or "")
    return TempMailMessage(
        id=message_id, from_address=from_address, subject=subject, text=text, html=html
    )


class CFWorkerTempMailProvider:
    """Temp mail provider backed by a deployed cloudflare_temp_email Worker.

    Reads cf_worker_* settings live on every call so saving new credentials
    in the settings page takes effect without a restart.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create_mailbox(self, requested_address: str | None = None) -> ProviderMailbox:
        base_url, admin_key, custom_auth = self._require_config()
        name, domain = _split_address(requested_address)
        if not name:
            alphabet: str = string.ascii_lowercase + string.digits
            name = "".join(secrets.choice(alphabet) for _ in range(8))
        if not domain:
            domain = self._default_domain()
        payload: dict[str, Any] = {"name": name, "enablePrefix": False}
        if domain:
            payload["domain"] = domain
        headers: dict[str, str] = {
            **_BROWSER_HEADERS,
            "Content-Type": "application/json",
            "x-admin-auth": admin_key,
        }
        if custom_auth:
            headers["x-custom-auth"] = custom_auth
        status, body = _http_request("POST", f"{base_url}/admin/new_address", headers, payload)
        if not 200 <= status < 300:
            raise TempMailProviderError(f"CF Worker 创建邮箱失败 HTTP {status}: {body[:200]}")
        data: dict[str, Any] = _parse_json_object(body)
        address: str = str(data.get("address") or "").strip()
        jwt: str = str(data.get("jwt") or "").strip()
        address_id: str = str(data.get("address_id") or data.get("id") or "").strip()
        if not address or not jwt:
            raise TempMailProviderError("CF Worker 未返回邮箱地址或访问凭证")
        return ProviderMailbox(
            provider_mailbox_id=json.dumps({"id": address_id, "jwt": jwt}),
            address=address,
        )

    def list_messages(
        self, provider_mailbox_id: str
    ) -> list[TempMailMessage | Mapping[str, str] | TempMailMessageLike]:
        base_url, _admin_key, custom_auth = self._require_config()
        jwt: str = _extract_jwt(provider_mailbox_id)
        if not jwt:
            raise TempMailProviderError("临时邮箱缺少访问凭证, 请删除后重新创建")
        headers: dict[str, str] = {**_BROWSER_HEADERS, "Authorization": f"Bearer {jwt}"}
        if custom_auth:
            headers["x-custom-auth"] = custom_auth
        status, body = _http_request("GET", f"{base_url}/api/mails?limit=100&offset=0", headers)
        if not 200 <= status < 300:
            raise TempMailProviderError(f"CF Worker 读取邮件失败 HTTP {status}: {body[:200]}")
        data: dict[str, Any] = _parse_json_object(body)
        raw_mails: Any = data.get("results") or data.get("mails") or []
        if not isinstance(raw_mails, list):
            raise TempMailProviderError("CF Worker 邮件列表字段格式错误")
        messages: list[TempMailMessage | Mapping[str, str] | TempMailMessageLike] = [
            _normalize_message(item) for item in raw_mails if isinstance(item, dict)
        ]
        return messages

    def _require_config(self) -> tuple[str, str, str]:
        base_url: str = get_setting(self._settings, "cf_worker_base_url").strip().rstrip("/")
        admin_key: str = get_setting(self._settings, "cf_worker_admin_key").strip()
        custom_auth: str = get_setting(self._settings, "cf_worker_custom_auth").strip()
        if not base_url or not admin_key:
            raise MissingTempMailProviderError(
                "CF Worker 未配置: 请在系统设置-临时邮箱中填写 Worker URL 和 Admin Key"
            )
        return base_url, admin_key, custom_auth

    def _default_domain(self) -> str:
        default: str = get_setting(self._settings, "cf_worker_default_domain").strip()
        if not default:
            default = get_setting(self._settings, "temp_mail_default_domain").strip()
        if default:
            return default.lstrip("@")
        try:
            domains: Any = json.loads(get_setting(self._settings, "cf_worker_domains") or "[]")
        except ValueError:
            domains = []
        if isinstance(domains, list):
            for item in domains:
                name: str = str(item).strip()
                if name:
                    return name.lstrip("@")
        return ""
