from unittest.mock import patch

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate
from hx_email.server.mail import EmailAccountMailbox, MailboxMessage
from hx_email.server.mail.email_accounts import add_email_account

API = "/api/v1"


class FakeIMAP:
    def __init__(self) -> None:
        self.login_args: tuple[str, str] | None = None

    def _simple_command(self, _command: str, _payload: str) -> tuple[str, list[bytes]]:
        return "OK", []

    def login(self, username: str, password: str) -> tuple[str, list[bytes]]:
        self.login_args = (username, password)
        return "OK", []

    def select(self, _folder: str, readonly: bool = True) -> tuple[str, list[bytes]]:
        _ = readonly
        return "OK", []

    def uid(self, command: str, *args: object) -> tuple[str, list[bytes]]:
        _ = args
        if command == "SEARCH":
            return "OK", [b""]
        return "OK", []

    def close(self) -> tuple[str, list[bytes]]:
        return "OK", []

    def logout(self) -> tuple[str, list[bytes]]:
        return "OK", []


class FailingMailboxProvider:
    def __init__(self, error: Exception) -> None:
        self.error: Exception = error

    def read_messages(
        self,
        email_account: EmailAccountMailbox,
        folder: str = "inbox",
        skip: int = 0,
        top: int = 50,
        since_uid: str = "",
    ) -> list[MailboxMessage | dict[str, object]]:
        _ = (email_account, folder, skip, top, since_uid)
        raise self.error


def login_admin(client: TestClient, settings: Settings) -> dict[str, str]:
    session = client.post(
        f"{API}/auth/login",
        json={"username": settings.admin_username, "password": settings.admin_password},
    ).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def test_gmail_provider_import_stores_app_password_as_imap_password(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)

    imported = client.post(
        f"{API}/email-accounts/import",
        json={
            "provider": "gmail",
            "text": "llh282000500@gmail.com----gmail-app-pass",
        },
        headers=headers,
    )
    accounts = client.get(f"{API}/email-accounts", headers=headers)

    account = accounts.json()["accounts"][0]
    assert imported.status_code == 201
    assert imported.json()["imported"] == 1
    assert account["provider"] == "gmail"
    assert account["imap_host"] == "imap.gmail.com"
    assert account["imap_port"] == 993
    assert account["imap_password"] == "gmail-app-pass"
    assert account["refresh_token"] == ""


def test_auto_import_stores_gmail_app_password_as_imap_password(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)

    imported = client.post(
        f"{API}/email-accounts/import",
        json={
            "provider": "auto",
            "text": "llh282000500@gmail.com----gmail-app-pass",
        },
        headers=headers,
    )
    accounts = client.get(f"{API}/email-accounts", headers=headers)

    account = accounts.json()["accounts"][0]
    assert imported.status_code == 201
    assert imported.json()["imported"] == 1
    assert account["provider"] == "gmail"
    assert account["imap_password"] == "gmail-app-pass"
    assert account["refresh_token"] == ""


def test_gmail_fetch_uses_imported_imap_app_password(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)
    client.post(
        f"{API}/email-accounts/import",
        json={
            "provider": "gmail",
            "text": "llh282000500@gmail.com----gmail-app-pass",
        },
        headers=headers,
    )
    account = client.get(f"{API}/email-accounts", headers=headers).json()["accounts"][0]
    usable_email_id = account["primary_usable_email"]["id"]
    fake = FakeIMAP()

    with patch("hx_email.server.mail.imap.imap_provider.imaplib.IMAP4_SSL", return_value=fake):
        result = client.post(f"{API}/usable-emails/{usable_email_id}/fetch-emails", headers=headers)

    assert result.status_code == 200
    assert fake.login_args == ("llh282000500@gmail.com", "gmail-app-pass")
    assert "账户没有配置密码" not in result.json()["error"]


def test_gmail_fetch_uses_legacy_refresh_token_app_password(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)
    add_email_account(
        settings,
        1,
        "gmail",
        "llh282000500@gmail.com",
        "llh282000500@gmail.com",
        "imap.gmail.com",
        993,
        "llh282000500@gmail.com",
        "",
        "",
        "legacy-gmail-app-pass",
    )
    account = client.get(f"{API}/email-accounts", headers=headers).json()["accounts"][0]
    usable_email_id = account["primary_usable_email"]["id"]
    fake = FakeIMAP()

    with patch("hx_email.server.mail.imap.imap_provider.imaplib.IMAP4_SSL", return_value=fake):
        result = client.post(f"{API}/usable-emails/{usable_email_id}/fetch-emails", headers=headers)

    assert result.status_code == 200
    assert fake.login_args == ("llh282000500@gmail.com", "legacy-gmail-app-pass")
    assert "账户没有配置密码" not in result.json()["error"]


def test_gmail_detail_exposes_legacy_refresh_token_app_password(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    headers = login_admin(client, settings)
    account = add_email_account(
        settings,
        1,
        "gmail",
        "llh282000500@gmail.com",
        "llh282000500@gmail.com",
        "imap.gmail.com",
        993,
        "llh282000500@gmail.com",
        "",
        "",
        "legacy-gmail-app-pass",
    )

    detail = client.get(f"{API}/email-accounts/{account.id}", headers=headers)

    assert detail.status_code == 200
    assert detail.json()["imap_password"] == "legacy-gmail-app-pass"
    assert detail.json()["has_imap_password"] is True


def test_gmail_authentication_failure_returns_app_password_hint(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    error = RuntimeError(
        "IMAP login failed (wrong password/app-password): "
        "b'[AUTHENTICATIONFAILED] Invalid credentials (Failure)'"
    )
    client = TestClient(create_app(settings, mailbox_provider=FailingMailboxProvider(error)))
    headers = login_admin(client, settings)
    client.post(
        f"{API}/email-accounts/import",
        json={
            "provider": "gmail",
            "text": "llh282000500@gmail.com----gmail-app-pass",
        },
        headers=headers,
    )
    account = client.get(f"{API}/email-accounts", headers=headers).json()["accounts"][0]
    usable_email_id = account["primary_usable_email"]["id"]

    result = client.post(f"{API}/usable-emails/{usable_email_id}/fetch-emails", headers=headers)

    assert result.status_code == 200
    message: str = result.json()["error"]
    assert "Gmail IMAP 认证失败" in message
    assert "App Password" in message
    assert "不要使用 Gmail 登录密码" in message
    assert "AUTHENTICATIONFAILED" in message
