from dataclasses import dataclass
from sqlite3 import Row

from hx_email.config import Settings
from hx_email.database import connect

SMTP_BY_PROVIDER: dict[str, tuple[str, int]] = {
    "outlook": ("smtp-mail.outlook.com", 587),
    "gmail": ("smtp.gmail.com", 587),
    "qq": ("smtp.qq.com", 587),
    "163": ("smtp.163.com", 465),
    "126": ("smtp.126.com", 465),
    "yahoo": ("smtp.mail.yahoo.com", 587),
}


@dataclass(frozen=True)
class SendCredentials:
    usable_email_id: int
    email_account_id: int
    from_address: str
    username: str
    password: str
    smtp_host: str
    smtp_port: int
    security: str
    credential_strategy: str


@dataclass(frozen=True)
class CredentialProblem:
    code: str
    message: str
    usable_email_id: int | None
    email_account_id: int | None
    from_address: str
    smtp_host: str
    smtp_port: int | None
    security: str
    actions: tuple[str, ...]


@dataclass(frozen=True)
class CredentialResolution:
    exists: bool
    credentials: SendCredentials | None
    problem: CredentialProblem | None


def resolve_send_credentials(
    settings: Settings, user_id: int, usable_email_id: int
) -> CredentialResolution:
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT ue.id AS usable_email_id, ue.address AS usable_address,
                   ue.email_account_id,
                   ea.id AS account_id, ea.provider, ea.primary_address,
                   ea.imap_host, ea.username, ea.imap_password,
                   ea.client_id, ea.refresh_token
            FROM usable_emails ue
            LEFT JOIN email_accounts ea
                ON ea.id = ue.email_account_id AND ea.user_id = ue.user_id
            WHERE ue.id = ? AND ue.user_id = ?
            """,
            (usable_email_id, user_id),
        ).fetchone()
    if row is None:
        return CredentialResolution(False, None, None)
    if row["account_id"] is None:
        return CredentialResolution(True, None, build_unlinked_problem(row))
    credentials = build_credentials(row)
    if credentials is not None:
        return CredentialResolution(True, credentials, None)
    return CredentialResolution(True, None, build_missing_config_problem(row))


def build_credentials(row: Row) -> SendCredentials | None:
    smtp_host, smtp_port = infer_smtp_server(row)
    username: str = str(row["username"] or "").strip() or str(row["primary_address"] or "").strip()
    password: str = str(row["imap_password"] or "").strip()
    client_id: str = str(row["client_id"] or "").strip()
    refresh_token: str = str(row["refresh_token"] or "").strip()
    if not password and not client_id and refresh_token:
        password = refresh_token
    if not smtp_host or not username or not password:
        return None
    return SendCredentials(
        usable_email_id=int(row["usable_email_id"]),
        email_account_id=int(row["account_id"]),
        from_address=username,
        username=username,
        password=password,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        security="ssl" if smtp_port == 465 else "starttls",
        credential_strategy="email_account_smtp_password",
    )


def infer_smtp_server(row: Row) -> tuple[str, int]:
    provider: str = str(row["provider"] or "").strip().lower()
    if provider in SMTP_BY_PROVIDER:
        return SMTP_BY_PROVIDER[provider]
    imap_host: str = str(row["imap_host"] or "").strip()
    if imap_host.startswith("imap."):
        return f"smtp.{imap_host[5:]}", 587
    return "", 587


def build_unlinked_problem(row: Row) -> CredentialProblem:
    return CredentialProblem(
        code="unlinked_usable_email",
        message="This usable email is not linked to an email account with SMTP credentials.",
        usable_email_id=int(row["usable_email_id"]),
        email_account_id=None,
        from_address=str(row["usable_address"] or ""),
        smtp_host="",
        smtp_port=None,
        security="",
        actions=("Choose a usable email created from an email account.",),
    )


def build_missing_config_problem(row: Row) -> CredentialProblem:
    smtp_host, smtp_port = infer_smtp_server(row)
    missing_host: bool = not smtp_host
    code: str = "missing_smtp_host" if missing_host else "missing_smtp_password"
    action: str = (
        "Set an IMAP host that can map to SMTP, or use a supported provider."
        if missing_host
        else "Set the email account app password in IMAP password."
    )
    return CredentialProblem(
        code=code,
        message="The selected email account is missing SMTP-compatible sending credentials.",
        usable_email_id=int(row["usable_email_id"]),
        email_account_id=int(row["account_id"]),
        from_address=str(row["primary_address"] or row["usable_address"] or ""),
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        security="ssl" if smtp_port == 465 else "starttls",
        actions=(action,),
    )
