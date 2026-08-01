"""External adapters for new-mail forwarding and notification pipelines."""

from __future__ import annotations

import json
import os
import smtplib
import subprocess
import urllib.error
import urllib.request
from email.message import EmailMessage
from pathlib import Path

from hx_email.config import Settings
from hx_email.server.mail.verification.extract import extract_verification_code
from hx_email.server.notifications.models import DeliveryChannel, StoredMessageEvent
from hx_email.server.settings_service import get_setting

DEFAULT_TIMEOUT_SECONDS: int = 15
MAX_RESPONSE_CHARS: int = 1000


def _event_payload(event: StoredMessageEvent) -> dict[str, object]:
    verification_code: str | None = extract_verification_code(f"{event.subject}\n{event.body}")
    return {
        "event": "new_mail",
        "message_id": event.id,
        "user_id": event.user_id,
        "usable_email": {
            "id": event.usable_email_id,
            "address": event.address,
            "group_id": event.group_id,
            "group_name": event.group_name,
        },
        "message": {
            "from": event.from_address,
            "to": event.recipient_address or event.address,
            "subject": event.subject,
            "body": event.body,
            "received_at": event.received_at,
            "verification_code": verification_code,
        },
    }


def _smtp_port(settings: Settings) -> int:
    raw_value: str = get_setting(settings, "email_notification_smtp_port", "587")
    try:
        return int(raw_value)
    except ValueError:
        return 587


def _send_email(settings: Settings, event: StoredMessageEvent) -> None:
    recipient: str = get_setting(settings, "email_notification_recipient", "")
    smtp_host: str = get_setting(settings, "email_notification_smtp_host", "")
    smtp_user: str = get_setting(settings, "email_notification_smtp_user", "")
    smtp_password: str = get_setting(settings, "email_notification_smtp_password", "")
    smtp_port: int = _smtp_port(settings)
    if not recipient or not smtp_host:
        raise RuntimeError("Email forwarding requires recipient and SMTP host")
    message = EmailMessage()
    message["Subject"] = f"Fwd: {event.subject or '(no subject)'}"
    message["From"] = smtp_user or "hx-email@localhost"
    message["To"] = recipient
    if event.from_address:
        message["Reply-To"] = event.from_address
    body: str = (
        f"Forwarded by HX Email\n\n"
        f"Mailbox: {event.address}\n"
        f"From: {event.from_address}\n"
        f"To: {event.recipient_address or event.address}\n"
        f"Received: {event.received_at}\n"
        f"Subject: {event.subject}\n\n{event.body}"
    )
    message.set_content(body)
    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=DEFAULT_TIMEOUT_SECONDS) as client:
            if smtp_user and smtp_password:
                client.login(smtp_user, smtp_password)
            client.send_message(message)
        return
    with smtplib.SMTP(smtp_host, smtp_port, timeout=DEFAULT_TIMEOUT_SECONDS) as client:
        client.starttls()
        if smtp_user and smtp_password:
            client.login(smtp_user, smtp_password)
        client.send_message(message)


def _open_json_request(
    url: str,
    payload: dict[str, object],
    headers: dict[str, str],
    *,
    proxy_url: str = "",
) -> tuple[int, str]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    opener: urllib.request.OpenerDirector = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        if proxy_url
        else urllib.request.ProxyHandler({})
    )
    try:
        with opener.open(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            body: str = response.read().decode("utf-8", errors="replace")
            return int(response.status), body
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        return int(error.code), body


def _send_webhook(settings: Settings, event: StoredMessageEvent) -> None:
    url: str = get_setting(settings, "webhook_notification_url", "")
    token: str = get_setting(settings, "webhook_notification_token", "")
    if not url:
        raise RuntimeError("Webhook URL is not configured")
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"} if token else {}
    status_code, response_body = _open_json_request(url, _event_payload(event), headers)
    if not 200 <= status_code < 300:
        raise RuntimeError(
            f"Webhook returned HTTP {status_code}: {response_body[:MAX_RESPONSE_CHARS]}"
        )


def _send_telegram(settings: Settings, event: StoredMessageEvent) -> None:
    token: str = get_setting(settings, "telegram_bot_token", "")
    chat_id: str = get_setting(settings, "telegram_chat_id", "")
    proxy_url: str = get_setting(settings, "telegram_proxy_url", "")
    if not token or not chat_id:
        raise RuntimeError("Telegram Bot Token and Chat ID are not configured")
    code: str | None = extract_verification_code(f"{event.subject}\n{event.body}")
    lines: list[str] = [
        f"New mail: {event.address}",
        f"From: {event.from_address or '-'}",
        f"Subject: {event.subject or '(no subject)'}",
    ]
    if code:
        lines.append(f"Verification code: {code}")
    url: str = f"https://api.telegram.org/bot{token}/sendMessage"
    status_code, response_body = _open_json_request(
        url,
        {"chat_id": chat_id, "text": "\n".join(lines)},
        {},
        proxy_url=proxy_url,
    )
    if not 200 <= status_code < 300:
        raise RuntimeError(
            f"Telegram returned HTTP {status_code}: {response_body[:MAX_RESPONSE_CHARS]}"
        )
    try:
        response_data: object = json.loads(response_body)
    except json.JSONDecodeError as error:
        raise RuntimeError("Telegram returned invalid JSON") from error
    if not isinstance(response_data, dict) or response_data.get("ok") is not True:
        raise RuntimeError(f"Telegram rejected the message: {response_body[:MAX_RESPONSE_CHARS]}")


def _script_timeout(settings: Settings) -> int:
    raw_value: str = get_setting(settings, "script_notification_timeout", "15")
    try:
        parsed_value: int = int(raw_value)
    except ValueError:
        parsed_value = DEFAULT_TIMEOUT_SECONDS
    return min(max(parsed_value, 1), 300)


def _resolve_script(path_value: str) -> Path:
    if not path_value:
        raise RuntimeError("Shell pipeline path is not configured")
    script_path: Path = Path(path_value).expanduser().resolve()
    if script_path.suffix.lower() != ".sh" or not script_path.is_file():
        raise RuntimeError("Shell pipeline must point to an existing .sh file")
    return script_path


def _run_script(path_value: str, payload: dict[str, object], timeout_seconds: int) -> str:
    script_path: Path = _resolve_script(path_value)
    environment: dict[str, str] = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "HX_EMAIL_EVENT": str(payload.get("event", "new_mail")),
    }
    result = subprocess.run(
        ["/bin/sh", str(script_path)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
        cwd=str(script_path.parent),
        env=environment,
    )
    if result.returncode != 0:
        detail: str = (result.stderr or result.stdout or "script failed").strip()
        raise RuntimeError(f"Shell pipeline exited with {result.returncode}: {detail[:1000]}")
    return result.stdout.strip()[:MAX_RESPONSE_CHARS]


def _send_script(settings: Settings, event: StoredMessageEvent) -> None:
    path_value: str = get_setting(settings, "script_notification_path", "")
    _run_script(path_value, _event_payload(event), _script_timeout(settings))


def send_delivery(
    settings: Settings,
    event: StoredMessageEvent,
    channel: DeliveryChannel,
) -> None:
    if channel == "email":
        _send_email(settings, event)
    elif channel == "telegram":
        _send_telegram(settings, event)
    elif channel == "webhook":
        _send_webhook(settings, event)
    elif channel == "script":
        _send_script(settings, event)
    else:
        raise RuntimeError(f"Unsupported delivery channel: {channel}")


def run_script_test(
    settings: Settings,
    path_value: str,
    timeout_seconds: int | None = None,
) -> str:
    payload: dict[str, object] = {
        "event": "test",
        "message": "HX Email shell pipeline test",
    }
    effective_timeout: int = (
        _script_timeout(settings) if timeout_seconds is None else min(max(timeout_seconds, 1), 300)
    )
    return _run_script(path_value, payload, effective_timeout)
