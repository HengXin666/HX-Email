"""Settings test/validate endpoints (Telegram, Email, Webhook, AI, Cron, CF Worker)."""

import json
import smtplib
import urllib.error
import urllib.request
from datetime import UTC, datetime
from email.mime.text import MIMEText
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, status

from hx_email.api.dependencies import require_user
from hx_email.api.schemas import (
    CFWorkerSyncRequest,
    CronValidateRequest,
    EmailTestRequest,
    TelegramTestRequest,
    VerificationAITestRequest,
    WebhookTestRequest,
)
from hx_email.config import Settings
from hx_email.server.settings_service import get_setting

try:
    from croniter import CroniterBadCronError
    from croniter import croniter as _croniter_cls

    HAS_CRONITER: bool = True
except ImportError:
    _croniter_cls = None
    CroniterBadCronError = ValueError
    HAS_CRONITER = False


def _http_error_body(exc: urllib.error.HTTPError) -> str:
    return exc.read().decode("utf-8", errors="replace")


def _json_post(
    url: str,
    data: dict[str, object],
    headers: dict[str, str] | None = None,
    timeout: int = 15,
    proxy_url: str | None = None,
) -> tuple[int, str]:
    """Helper: POST JSON and return (status, body)."""
    payload: bytes = json.dumps(data).encode("utf-8")
    req_headers: dict[str, str] = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=payload, headers=req_headers)
    opener: urllib.request.OpenerDirector
    if proxy_url:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"https": proxy_url}))
    else:
        opener = urllib.request.build_opener()
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, _http_error_body(exc)


def _json_get(
    url: str, headers: dict[str, str] | None = None, timeout: int = 15
) -> tuple[int, str]:
    """Helper: GET JSON and return (status, body)."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, _http_error_body(exc)


def register_settings_test_routes(router: APIRouter, settings: Settings) -> None:
    """Register all settings test/validate endpoints."""

    @router.post("/settings/validate-cron")
    def validate_cron(
        payload: CronValidateRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Validate a cron expression and return next run times."""
        require_user(settings, authorization)
        expr: str = payload.cron_expression.strip()
        if not expr:
            return {"valid": False, "next_runs": [], "error": "Empty expression"}
        if HAS_CRONITER:
            assert _croniter_cls is not None
            try:
                cron = _croniter_cls(expr, datetime.now(tz=UTC))
                next_runs: list[str] = [cron.get_next(datetime).isoformat() for _ in range(5)]
                return {"valid": True, "next_runs": next_runs}
            except (ValueError, KeyError, CroniterBadCronError) as exc:
                return {"valid": False, "next_runs": [], "error": str(exc)}
        parts: list[str] = expr.split()
        if len(parts) != 5:
            return {"valid": False, "next_runs": [], "error": "Cron expression must have 5 fields"}
        return {"valid": True, "next_runs": [], "message": "croniter not available"}

    @router.post("/settings/telegram-test")
    def telegram_test(
        payload: TelegramTestRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Send a test message via Telegram Bot API."""
        require_user(settings, authorization)
        bot_token: str = payload.bot_token or get_setting(settings, "telegram_bot_token")
        chat_id: str = payload.chat_id or get_setting(settings, "telegram_chat_id")
        proxy_url: str | None = (
            payload.proxy_url or get_setting(settings, "telegram_proxy_url") or None
        )
        if not bot_token or not chat_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="bot_token and chat_id are required",
            )
        url: str = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        _status_code, body = _json_post(
            url,
            {"chat_id": chat_id, "text": "HX-Email Test Message"},
            timeout=15,
            proxy_url=proxy_url,
        )
        result: dict[str, Any] = json.loads(body)
        return {"success": result.get("ok", False), "response": result}

    @router.post("/settings/email-test")
    def email_test(
        payload: EmailTestRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Send a test email via SMTP."""
        require_user(settings, authorization)
        smtp_host: str | None = (
            payload.smtp_host or get_setting(settings, "email_notification_smtp_host") or None
        )
        smtp_port: int | None = payload.smtp_port
        if smtp_port is None:
            port_str: str = get_setting(settings, "email_notification_smtp_port", "587")
            smtp_port = int(port_str) if port_str else 587
        smtp_user: str | None = (
            payload.smtp_user or get_setting(settings, "email_notification_smtp_user") or None
        )
        smtp_password: str | None = (
            payload.smtp_password
            or get_setting(settings, "email_notification_smtp_password")
            or None
        )
        if not smtp_host or not payload.recipient:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="smtp_host and recipient are required",
            )
        msg = MIMEText("This is a test email from HX-Email.", "plain", "utf-8")
        msg["Subject"] = "HX-Email Test"
        msg["From"] = smtp_user or "test@example.com"
        msg["To"] = payload.recipient
        try:
            if smtp_port == 465:
                with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
                    if smtp_user and smtp_password:
                        server.login(smtp_user, smtp_password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                    server.starttls()
                    if smtp_user and smtp_password:
                        server.login(smtp_user, smtp_password)
                    server.send_message(msg)
            return {"success": True, "message": f"Test email sent to {payload.recipient}"}
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    @router.post("/settings/webhook-test")
    def webhook_test(
        payload: WebhookTestRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Send a test POST to the webhook URL."""
        require_user(settings, authorization)
        url: str = payload.url
        token: str | None = (
            payload.token or get_setting(settings, "webhook_notification_token") or None
        )
        if not url:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="url is required"
            )
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        status_code, body = _json_post(
            url, {"test": True, "message": "HX-Email webhook test"}, headers, timeout=15
        )
        return {"success": True, "status_code": status_code, "response": body[:1000]}

    @router.post("/settings/verification-ai-test")
    def verification_ai_test(
        payload: VerificationAITestRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Call AI API to extract a verification code from sample content."""
        require_user(settings, authorization)
        base_url: str = get_setting(settings, "verification_ai_base_url")
        model: str = get_setting(settings, "verification_ai_model")
        api_key: str = get_setting(settings, "verification_ai_api_key")
        if not base_url or not model:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="AI base_url and model must be configured",
            )
        subject: str = payload.subject or "Your verification code"
        body: str = payload.body or "Your verification code is: 123456"
        body_html: str | None = (
            payload.body_html or "<p>Your verification code is: <b>123456</b></p>"
        )
        code_length: int = payload.code_length or 6
        code_regex: str = payload.code_regex or ""
        prompt_parts: list[str] = [
            "Extract the verification code from the following email content.",
            "Return ONLY the code, nothing else.",
            f"Subject: {subject}",
            f"Body: {body}",
        ]
        if body_html:
            prompt_parts.append(f"HTML Body: {body_html}")
        if code_regex:
            prompt_parts.append(f"The code should match regex: {code_regex}")
        else:
            prompt_parts.append(f"The code should be {code_length} digits.")
        prompt: str = "\n".join(prompt_parts)
        api_url: str = f"{base_url.rstrip('/')}/v1/chat/completions"
        api_headers: dict[str, str] = {}
        if api_key:
            api_headers["Authorization"] = f"Bearer {api_key}"
        try:
            _status_code, body_text = _json_post(
                api_url,
                {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 50,
                    "temperature": 0,
                },
                api_headers,
                timeout=30,
            )
            result: dict[str, Any] = json.loads(body_text)
            content: str = result["choices"][0]["message"]["content"]
            return {"success": True, "code": content.strip(), "raw": result}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @router.post("/settings/cf-worker-sync-domains")
    def cf_worker_sync_domains(
        payload: CFWorkerSyncRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Fetch domains from a Cloudflare Worker admin endpoint."""
        require_user(settings, authorization)
        worker_url: str = payload.worker_url or get_setting(settings, "cf_worker_base_url")
        admin_key: str = payload.admin_key or get_setting(settings, "cf_worker_admin_key")
        if not worker_url:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="worker_url is required"
            )
        headers: dict[str, str] = {}
        if admin_key:
            headers["Authorization"] = f"Bearer {admin_key}"
        url: str = f"{worker_url.rstrip('/')}/admin/domains"
        try:
            _status_code, body = _json_get(url, headers, timeout=15)
            result: dict[str, Any] = json.loads(body)
            domains: object = result.get("domains", result)
            return {"success": True, "domains": domains}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
