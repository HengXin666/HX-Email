from dataclasses import dataclass

from hx_email.config import Settings
from hx_email.server.mail.impl.sending.credentials import (
    CredentialProblem,
    SendCredentials,
    resolve_send_credentials,
)
from hx_email.server.mail.impl.sending.delivery import deliver_debug_email

CREDENTIAL_POLICY = "Uses the selected account provider-native OAuth or SMTP credentials."


@dataclass(frozen=True)
class SendDebugEmailResult:
    success: bool
    code: str
    message: str
    credential_policy: str
    credential_strategy: str
    from_address: str
    to_address: str
    usable_email_id: int | None
    email_account_id: int | None
    smtp_host: str
    smtp_port: int | None
    security: str
    actions: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "success": self.success,
            "code": self.code,
            "message": self.message,
            "credential_policy": self.credential_policy,
            "credential_strategy": self.credential_strategy,
            "from_address": self.from_address,
            "to_address": self.to_address,
            "usable_email_id": self.usable_email_id,
            "email_account_id": self.email_account_id,
            "smtp_host": self.smtp_host,
            "smtp_port": self.smtp_port,
            "security": self.security,
            "actions": list(self.actions),
        }


def send_debug_email(
    settings: Settings,
    user_id: int,
    usable_email_id: int,
    *,
    recipient: str,
    subject: str,
    body: str,
) -> SendDebugEmailResult | None:
    message_subject: str = subject.strip() or "HX-Email debug email"
    message_body: str = body.strip() or "This is a debug email sent by HX-Email."
    resolution = resolve_send_credentials(settings, user_id, usable_email_id)
    if not resolution.exists:
        return None
    to_address: str = recipient.strip()
    if resolution.problem is not None:
        to_address = to_address or resolution.problem.from_address
        return build_problem_result(resolution.problem, to_address)
    credentials = resolution.credentials
    if credentials is None:
        return build_input_error(
            "missing_credentials", "Sending credentials are missing.", usable_email_id
        )
    to_address = to_address or credentials.from_address
    try:
        deliver_debug_email(settings, credentials, to_address, message_subject, message_body)
    except Exception as error:
        return build_delivery_error(credentials, to_address, error)
    return build_success_result(credentials, to_address)


def build_success_result(credentials: SendCredentials, to_address: str) -> SendDebugEmailResult:
    return SendDebugEmailResult(
        success=True,
        code="sent",
        message=f"Debug email sent to {to_address}.",
        credential_policy=CREDENTIAL_POLICY,
        credential_strategy=credentials.credential_strategy,
        from_address=credentials.from_address,
        to_address=to_address,
        usable_email_id=credentials.usable_email_id,
        email_account_id=credentials.email_account_id,
        smtp_host=credentials.smtp_host,
        smtp_port=credentials.smtp_port,
        security=credentials.security,
        actions=(),
    )


def build_problem_result(problem: CredentialProblem, to_address: str) -> SendDebugEmailResult:
    return SendDebugEmailResult(
        success=False,
        code=problem.code,
        message=problem.message,
        credential_policy=CREDENTIAL_POLICY,
        credential_strategy="email_account_smtp_password",
        from_address=problem.from_address,
        to_address=to_address,
        usable_email_id=problem.usable_email_id,
        email_account_id=problem.email_account_id,
        smtp_host=problem.smtp_host,
        smtp_port=problem.smtp_port,
        security=problem.security,
        actions=problem.actions,
    )


def build_delivery_error(
    credentials: SendCredentials, to_address: str, error: Exception
) -> SendDebugEmailResult:
    return SendDebugEmailResult(
        success=False,
        code="delivery_failed",
        message=str(error),
        credential_policy=CREDENTIAL_POLICY,
        credential_strategy=credentials.credential_strategy,
        from_address=credentials.from_address,
        to_address=to_address,
        usable_email_id=credentials.usable_email_id,
        email_account_id=credentials.email_account_id,
        smtp_host=credentials.smtp_host,
        smtp_port=credentials.smtp_port,
        security=credentials.security,
        actions=delivery_error_actions(credentials),
    )


def delivery_error_actions(credentials: SendCredentials) -> tuple[str, ...]:
    if credentials.credential_strategy == "gmail_oauth_smtp":
        return (
            "在 Google OAuth 页面重新授权该账号, 并确认已授予完整 Gmail 邮件权限。",
            "确认 Google OAuth Client ID、Client Secret 和账号地址匹配。",
        )
    if credentials.credential_strategy == "outlook_graph_send_mail":
        return (
            "在 Token 工具选择 Graph 邮件预设 (Mail.Read + Mail.Send)。",
            "保存新配置后强制重新授权该 Microsoft 账号; 旧 refresh token 不会自动获得新权限。",
        )
    return ("检查服务商应用专用密码、SMTP 地址、端口和 SMTP 开关。",)


def build_input_error(code: str, message: str, usable_email_id: int) -> SendDebugEmailResult:
    return SendDebugEmailResult(
        success=False,
        code=code,
        message=message,
        credential_policy=CREDENTIAL_POLICY,
        credential_strategy="email_account_smtp_password",
        from_address="",
        to_address="",
        usable_email_id=usable_email_id,
        email_account_id=None,
        smtp_host="",
        smtp_port=None,
        security="",
        actions=("Fill the required send-mail fields.",),
    )
