"""Settings test endpoints for external delivery channels and AI extraction."""

import json
import smtplib
import urllib.error
import urllib.request
from email.mime.text import MIMEText
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from hx_email.api.dependencies import require_admin
from hx_email.api.schemas import (
    EmailTestRequest,
    TelegramTestRequest,
    VerificationAITestRequest,
    WebhookTestRequest,
)
from hx_email.config import Settings
from hx_email.server.notifications import test_script_pipeline
from hx_email.server.settings_service import get_setting


class ScriptTestRequest(BaseModel):
    path: str = ""
    timeout_seconds: int | None = None


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


def register_settings_test_routes(router: APIRouter, settings: Settings) -> None:
    """Register all settings test/validate endpoints."""

    @router.post("/settings/telegram-test")
    def telegram_test(
        payload: TelegramTestRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Send a test message via Telegram Bot API."""
        require_admin(settings, authorization)
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
        success: bool = result.get("ok") is True
        return {
            "success": success,
            "message": "Telegram test message sent" if success else str(result),
            "response": result,
        }

    @router.post("/settings/email-test")
    def email_test(
        payload: EmailTestRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Send a test email via SMTP."""
        require_admin(settings, authorization)
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
        require_admin(settings, authorization)
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
        success: bool = 200 <= status_code < 300
        return {
            "success": success,
            "message": (
                f"Webhook accepted the test message (HTTP {status_code})"
                if success
                else f"Webhook returned HTTP {status_code}"
            ),
            "status_code": status_code,
            "response": body[:1000],
        }

    @router.post("/settings/script-test")
    def script_test(
        payload: ScriptTestRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Run a shell pipeline with a harmless test event."""
        require_admin(settings, authorization)
        path_value: str = payload.path or get_setting(settings, "script_notification_path", "")
        return test_script_pipeline(settings, path_value, payload.timeout_seconds)

    @router.post("/settings/verification-ai-test")
    def verification_ai_test(
        payload: VerificationAITestRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Call AI API to extract a verification code from sample content."""
        require_admin(settings, authorization)
        base_url: str = payload.base_url or get_setting(settings, "verification_ai_base_url")
        model: str = payload.model_id or get_setting(settings, "verification_ai_model")
        api_key: str = payload.api_key or get_setting(settings, "verification_ai_api_key")
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
        normalized_base_url: str = base_url.rstrip("/")
        api_url: str = (
            f"{normalized_base_url}/chat/completions"
            if normalized_base_url.endswith("/v1")
            else f"{normalized_base_url}/v1/chat/completions"
        )
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
