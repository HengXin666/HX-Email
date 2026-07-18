from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.security import decrypt_secret, encrypt_secret
from hx_email.server.mail.email_accounts import add_email_account, get_email_account
from hx_email.server.settings_service import get_setting, set_setting


def test_secret_codec_encrypts_and_decrypts_with_configured_master_key(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, secret_key="test-master-key")

    encrypted = encrypt_secret(settings, "refresh-token")

    assert encrypted.startswith("enc:v1:")
    assert "refresh-token" not in encrypted
    assert decrypt_secret(settings, encrypted) == "refresh-token"


def test_refresh_tokens_and_google_secret_are_encrypted_at_rest(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, secret_key="test-master-key")
    migrate(settings)
    account = add_email_account(
        settings,
        1,
        "gmail",
        "owner@gmail.com",
        "Owner",
        client_id="client-id",
        refresh_token="refresh-token",
    )
    set_setting(settings, "google_oauth_client_secret", "client-secret")

    with connect(settings) as connection:
        token_row = connection.execute(
            "SELECT refresh_token FROM email_accounts WHERE id = ?", (account.id,)
        ).fetchone()
        setting_row = connection.execute(
            "SELECT value FROM system_settings WHERE key = 'google_oauth_client_secret'"
        ).fetchone()
    loaded = get_email_account(settings, 1, account.id)

    assert token_row is not None and str(token_row["refresh_token"]).startswith("enc:v1:")
    assert setting_row is not None and str(setting_row["value"]).startswith("enc:v1:")
    assert loaded is not None and loaded.refresh_token == "refresh-token"
    assert get_setting(settings, "google_oauth_client_secret") == "client-secret"


def test_migrate_encrypts_legacy_plaintext_refresh_tokens(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, secret_key="test-master-key")
    migrate(settings)
    with connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO email_accounts
                (id, user_id, provider, primary_address, display_name, refresh_token)
            VALUES (99, 1, 'outlook', 'legacy@example.com', 'Legacy', 'legacy-token')
            """
        )

    migrate(settings)

    with connect(settings) as connection:
        row = connection.execute(
            "SELECT refresh_token FROM email_accounts WHERE id = 99"
        ).fetchone()
    assert row is not None
    assert str(row["refresh_token"]).startswith("enc:v1:")
    assert decrypt_secret(settings, str(row["refresh_token"])) == "legacy-token"
