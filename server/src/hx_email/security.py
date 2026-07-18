import hashlib
import os
import secrets
import sqlite3
from base64 import b64decode, urlsafe_b64encode
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from hx_email.config import Settings

ENCRYPTED_PREFIX: str = "enc:v1:"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    algorithm, salt, expected_digest = password_hash.split("$", 2)
    if algorithm != "pbkdf2_sha256":
        return False
    actual_digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return secrets.compare_digest(actual_digest.hex(), expected_digest)


def secret_key_path(settings: Settings) -> Path:
    return settings.data_dir.resolve() / ".hx_email_secret_key"


def load_secret_key(settings: Settings) -> bytes:
    configured: str = settings.secret_key.strip()
    if configured:
        digest: bytes = hashlib.sha256(configured.encode()).digest()
        return urlsafe_b64encode(digest)

    path: Path = secret_key_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_bytes().strip()
    generated: bytes = Fernet.generate_key()
    try:
        descriptor: int = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_bytes().strip()
    try:
        os.write(descriptor, generated)
    finally:
        os.close(descriptor)
    return generated


def encrypt_secret(settings: Settings, value: str) -> str:
    if not value or value.startswith(ENCRYPTED_PREFIX):
        return value
    encrypted: str = Fernet(load_secret_key(settings)).encrypt(value.encode()).decode()
    return f"{ENCRYPTED_PREFIX}{encrypted}"


def decrypt_secret(settings: Settings, value: str) -> str:
    if not value or not value.startswith(ENCRYPTED_PREFIX):
        return value
    token: str = value.removeprefix(ENCRYPTED_PREFIX)
    try:
        return Fernet(load_secret_key(settings)).decrypt(token.encode()).decode()
    except InvalidToken as error:
        raise RuntimeError(
            "Stored secret cannot be decrypted; restore the original HX_EMAIL_SECRET_KEY"
        ) from error


def persist_rotated_refresh_token(
    settings: Settings,
    account_id: int,
    current_token: str,
    rotated_token: str,
) -> bool:
    normalized: str = rotated_token.strip()
    if not normalized or normalized == current_token.strip():
        return False
    with sqlite3.connect(settings.database_path) as connection:
        cursor = connection.execute(
            "UPDATE email_accounts SET refresh_token = ? "
            "WHERE id = ? AND provider IN ('outlook', 'hotmail')",
            (encrypt_secret(settings, normalized), account_id),
        )
    return cursor.rowcount == 1


def decode_legacy_base64(value: str) -> str:
    if not value:
        return ""
    try:
        return b64decode(value.encode(), validate=True).decode()
    except (ValueError, UnicodeDecodeError):
        return value


def migrate_stored_secrets(settings: Settings, connection: sqlite3.Connection) -> None:
    token_rows = connection.execute(
        "SELECT id, refresh_token FROM email_accounts WHERE refresh_token != ''"
    ).fetchall()
    for account_id, stored_token in token_rows:
        value: str = str(stored_token or "")
        if not value.startswith(ENCRYPTED_PREFIX):
            connection.execute(
                "UPDATE email_accounts SET refresh_token = ? WHERE id = ?",
                (encrypt_secret(settings, value), account_id),
            )

    setting_row = connection.execute(
        "SELECT value FROM system_settings WHERE key = 'google_oauth_client_secret'"
    ).fetchone()
    if setting_row is None:
        return
    stored_secret: str = str(setting_row[0] or "")
    if stored_secret and not stored_secret.startswith(ENCRYPTED_PREFIX):
        plaintext: str = decode_legacy_base64(stored_secret)
        connection.execute(
            "UPDATE system_settings SET value = ? WHERE key = 'google_oauth_client_secret'",
            (encrypt_secret(settings, plaintext),),
        )
