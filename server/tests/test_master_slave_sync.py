from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.cli import main
from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.security import decrypt_secret, load_secret_key
from hx_email.server.instance_backup import create_instance_backup
from hx_email.server.sync import apply_snapshot, run_sync
from hx_email.server.sync.impl.merge import load_rows


def build_master(settings: Settings, marker: str) -> None:
    migrate(settings)
    with connect(settings) as connection:
        connection.execute(
            "INSERT INTO groups (user_id, name, color) VALUES (1, ?, ?)",
            ("work", "#ff0000"),
        )
        connection.execute(
            "INSERT INTO tags (user_id, name, color) VALUES (1, ?, ?)",
            ("urgent", "#00ff00"),
        )
        connection.execute(
            "INSERT INTO email_accounts (user_id, provider, primary_address, refresh_token)"
            " VALUES (1, 'gmail', ?, ?)",
            (f"account-{marker}@example.com", f"refresh-{marker}"),
        )
        connection.execute(
            "INSERT INTO usable_emails (user_id, email_account_id, address, group_id,"
            " notify_enabled) VALUES (1, 1, ?, 1, 1)",
            (f"mail-{marker}@example.com",),
        )
        connection.execute("INSERT INTO usable_email_tags (usable_email_id, tag_id) VALUES (1, 1)")
        connection.execute("INSERT INTO platforms (user_id, name) VALUES (1, 'google')")
        connection.execute(
            "INSERT INTO platform_bindings (user_id, usable_email_id, platform_id, status,"
            " notes) VALUES (1, 1, 1, 'active', 'notes')"
        )
        connection.execute(
            "INSERT INTO temp_mailboxes (user_id, usable_email_id, provider,"
            " provider_mailbox_id) VALUES (1, 1, 'cf', ?)",
            (f"mailbox-{marker}",),
        )
        connection.execute("INSERT INTO mail_pool_entries (user_id, usable_email_id) VALUES (1, 1)")
        connection.execute(
            "INSERT INTO verification_readings (user_id, usable_email_id, code, certainty,"
            " subject) VALUES (1, 1, '654321', 'high', ?)",
            (f"subject-{marker}",),
        )
        connection.execute(
            "INSERT INTO fetched_messages (user_id, usable_email_id, email_account_id,"
            " from_address, recipient_address, subject, body, message_id, body_hash)"
            " VALUES (1, 1, 1, 'sender@example.com', ?, ?, 'body', 'msg-1', ?)",
            (f"mail-{marker}@example.com", f"hello-{marker}", f"hash-{marker}"),
        )
    static_file: Path = settings.data_dir.resolve() / "static" / "img" / "logo.txt"
    static_file.parent.mkdir(parents=True)
    static_file.write_text(f"logo-{marker}", encoding="utf-8")


def count_table(settings: Settings, table: str) -> int:
    with connect(settings) as connection:
        return len(load_rows(connection, table))


def test_sync_requires_master_configuration(tmp_path: Path) -> None:
    settings: Settings = Settings(data_dir=tmp_path / "slave", sync_url="", sync_token="")
    report = run_sync(settings)
    assert report.error
    assert "HX_EMAIL_SYNC_URL" in report.error
    assert report.tables == {}


def test_cli_sync_without_config_exits_nonzero(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HX_EMAIL_DATA_DIR", str(tmp_path / "runtime"))
    monkeypatch.delenv("HX_EMAIL_SYNC_URL", raising=False)
    monkeypatch.delenv("HX_EMAIL_SYNC_TOKEN", raising=False)

    assert main(["sync"]) == 1


def test_apply_snapshot_mirrors_master_data(tmp_path: Path) -> None:
    master_settings: Settings = Settings(
        data_dir=tmp_path / "master",
        admin_username="admin",
        admin_password="admin-password",
    )
    build_master(master_settings, "one")
    archive: bytes = create_instance_backup(master_settings)

    slave_settings: Settings = Settings(
        data_dir=tmp_path / "slave",
        admin_username="admin",
        admin_password="admin-password",
    )
    report = apply_snapshot(slave_settings, archive)

    assert report.error == ""
    assert report.files["static/img/logo.txt"] == "copied"
    assert report.files[".hx_email_secret_key"] == "copied"
    assert report.tables["users"] == 1
    assert report.tables["groups"] == 1
    assert report.tables["email_accounts"] == 1
    assert report.tables["usable_emails"] == 1
    assert report.tables["verification_readings"] == 1
    assert report.tables["fetched_messages"] == 1
    with connect(slave_settings) as connection:
        group_color: str = str(connection.execute("SELECT color FROM groups").fetchone()[0])
        stored_token: str = str(
            connection.execute("SELECT refresh_token FROM email_accounts").fetchone()[0]
        )
        stored_message: str = str(
            connection.execute("SELECT subject FROM fetched_messages").fetchone()[0]
        )
    assert group_color == "#ff0000"
    assert decrypt_secret(slave_settings, stored_token) == "refresh-one"
    assert stored_message == "hello-one"
    assert (slave_settings.data_dir.resolve() / "static" / "img" / "logo.txt").read_text(
        encoding="utf-8"
    ) == "logo-one"


def test_apply_snapshot_is_idempotent_and_incremental(tmp_path: Path) -> None:
    master_settings: Settings = Settings(
        data_dir=tmp_path / "master",
        admin_username="admin",
        admin_password="admin-password",
    )
    build_master(master_settings, "one")
    slave_settings: Settings = Settings(
        data_dir=tmp_path / "slave",
        admin_username="admin",
        admin_password="admin-password",
    )
    apply_snapshot(slave_settings, create_instance_backup(master_settings))

    second_report = apply_snapshot(slave_settings, create_instance_backup(master_settings))

    assert second_report.error == ""
    assert second_report.files["static/img/logo.txt"] == "unchanged"
    assert second_report.files[".hx_email_secret_key"] == "kept"
    for table, count in second_report.tables.items():
        assert count_table(slave_settings, table) == count
    assert count_table(slave_settings, "fetched_messages") == 1


def test_apply_snapshot_updates_existing_rows_and_appends_new_ones(tmp_path: Path) -> None:
    master_settings: Settings = Settings(
        data_dir=tmp_path / "master",
        admin_username="admin",
        admin_password="admin-password",
    )
    build_master(master_settings, "one")
    slave_settings: Settings = Settings(
        data_dir=tmp_path / "slave",
        admin_username="admin",
        admin_password="admin-password",
    )
    apply_snapshot(slave_settings, create_instance_backup(master_settings))

    with connect(master_settings) as connection:
        connection.execute("UPDATE groups SET color = '#111111' WHERE name = 'work'")
        connection.execute(
            "INSERT INTO fetched_messages (user_id, usable_email_id, email_account_id,"
            " from_address, recipient_address, subject, body, message_id, body_hash)"
            " VALUES (1, 1, 1, 'sender@example.com', 'mail-one@example.com', 'hello-two',"
            " 'body', 'msg-2', 'hash-two')"
        )

    report = apply_snapshot(slave_settings, create_instance_backup(master_settings))

    assert report.error == ""
    with connect(slave_settings) as connection:
        color: str = str(connection.execute("SELECT color FROM groups").fetchone()[0])
        subjects: list[str] = [
            str(row[0]) for row in connection.execute("SELECT subject FROM fetched_messages")
        ]
    assert color == "#111111"
    assert sorted(subjects) == ["hello-one", "hello-two"]


def test_apply_snapshot_keeps_local_data_and_secret_key(tmp_path: Path) -> None:
    master_settings: Settings = Settings(
        data_dir=tmp_path / "master",
        admin_username="admin",
        admin_password="admin-password",
    )
    build_master(master_settings, "one")
    archive: bytes = create_instance_backup(master_settings)

    slave_settings: Settings = Settings(
        data_dir=tmp_path / "slave",
        admin_username="local-admin",
        admin_password="local-password",
    )
    migrate(slave_settings)
    load_secret_key(slave_settings)
    slave_key: Path = slave_settings.data_dir.resolve() / ".hx_email_secret_key"
    slave_key_before: bytes = slave_key.read_bytes()
    with connect(slave_settings) as connection:
        connection.execute(
            "INSERT INTO groups (user_id, name, color) VALUES (1, 'local-group', '#333333')"
        )

    report = apply_snapshot(slave_settings, archive)

    assert report.error == ""
    assert slave_key.read_bytes() == slave_key_before
    assert report.files[".hx_email_secret_key"] == "kept"
    with connect(slave_settings) as connection:
        names: list[str] = [
            str(row[0]) for row in connection.execute("SELECT name FROM groups ORDER BY name")
        ]
    assert names == ["local-group", "work"]
    assert count_table(slave_settings, "fetched_messages") == 1


def test_snapshot_endpoint_requires_admin_and_reports_status(tmp_path: Path) -> None:
    settings: Settings = Settings(
        data_dir=tmp_path,
        admin_username="admin",
        admin_password="admin-password",
    )
    migrate(settings)
    client: TestClient = TestClient(create_app(settings))
    login_response = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin-password"}
    )
    admin_headers: dict[str, str] = {
        "Authorization": f"Bearer {login_response.json()['access_token']}"
    }

    assert client.get("/api/v1/admin/sync/snapshot").status_code == 401
    assert client.get("/api/v1/admin/sync/snapshot", headers=admin_headers).status_code == 200
    snapshot_response = client.get("/api/v1/admin/sync/snapshot", headers=admin_headers)
    assert snapshot_response.headers["content-type"] == "application/zip"
    status_response = client.get("/api/v1/sync/status", headers=admin_headers)
    assert status_response.status_code == 200
    assert status_response.json()["enabled"] is False
