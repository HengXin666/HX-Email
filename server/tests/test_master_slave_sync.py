from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.cli import main
from hx_email.config import Settings
from hx_email.database import connect, migrate
from hx_email.security import decrypt_secret, load_secret_key
from hx_email.server.instance_backup import create_instance_backup
from hx_email.server.sync import SyncReport, apply_snapshot, push_snapshot, run_sync
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


def test_sync_status_redacts_master_url(tmp_path: Path) -> None:
    from hx_email.server.sync.scheduler import (
        SyncScheduler,
        get_sync_status,
        register_sync_scheduler,
        unregister_sync_scheduler,
    )

    settings: Settings = Settings(
        data_dir=tmp_path / "slave",
        admin_username="admin",
        admin_password="admin-password",
        sync_url="https://internal-master.example.internal:18090",
        sync_token="secret-token",
    )
    migrate(settings)
    scheduler = SyncScheduler(settings)
    scheduler.last_run = "2026-08-10T00:00:00Z"
    scheduler.last_error = (
        "Could not reach master at https://internal-master.example.internal:18090: timed out"
    )
    sync_error = (
        "Could not reach master at https://internal-master.example.internal:18090: timed out"
    )
    scheduler.last_summary = {
        "error": sync_error,
        "tables": {},
        "files": {},
        "push": {
            "error": (
                "Could not reach master at https://internal-master.example.internal:18090:"
                " timed out"
            ),
        },
    }
    register_sync_scheduler(settings, scheduler)
    try:
        status: dict[str, object] = get_sync_status(settings)
    finally:
        unregister_sync_scheduler(settings, scheduler)

    assert "internal-master.example.internal" not in str(status["last_error"])
    assert "<master-url>" in str(status["last_error"])
    summary: dict[str, object] = dict(status["last_summary"])
    assert "internal-master.example.internal" not in str(summary.get("error", ""))
    assert "<master-url>" in str(summary.get("error", ""))
    push_summary: dict[str, object] = dict(summary["push"])
    assert "internal-master.example.internal" not in str(push_summary.get("error", ""))
    assert "<master-url>" in str(push_summary.get("error", ""))


def test_apply_snapshot_insert_only_preserves_local_rows(tmp_path: Path) -> None:
    master_settings: Settings = Settings(
        data_dir=tmp_path / "master",
        admin_username="admin",
        admin_password="admin-password",
    )
    build_master(master_settings, "one")
    with connect(master_settings) as connection:
        connection.execute(
            "INSERT INTO email_accounts (user_id, provider, primary_address, refresh_token)"
            " VALUES (1, 'gmail', 'master-extra@example.com', 'refresh-extra')"
        )

    slave_settings: Settings = Settings(
        data_dir=tmp_path / "slave",
        admin_username="admin",
        admin_password="admin-password",
    )
    build_master(slave_settings, "one")
    with connect(slave_settings) as connection:
        connection.execute("UPDATE groups SET color = '#222222' WHERE name = 'work'")
        connection.execute(
            "UPDATE email_accounts SET remark = 'slave-note'"
            " WHERE primary_address = 'account-one@example.com'"
        )

    report = apply_snapshot(
        slave_settings, create_instance_backup(master_settings), overwrite=False
    )

    assert report.error == ""
    with connect(slave_settings) as connection:
        color: str = str(
            connection.execute("SELECT color FROM groups WHERE name = 'work'").fetchone()[0]
        )
        remark: str = str(
            connection.execute(
                "SELECT remark FROM email_accounts"
                " WHERE primary_address = 'account-one@example.com'"
            ).fetchone()[0]
        )
        addresses: list[str] = [
            str(row[0])
            for row in connection.execute(
                "SELECT primary_address FROM email_accounts ORDER BY primary_address"
            )
        ]
    assert color == "#222222"
    assert remark == "slave-note"
    assert addresses == ["account-one@example.com", "master-extra@example.com"]


def test_push_endpoint_requires_admin(tmp_path: Path) -> None:
    settings: Settings = Settings(
        data_dir=tmp_path,
        admin_username="admin",
        admin_password="admin-password",
    )
    migrate(settings)
    client: TestClient = TestClient(create_app(settings))
    response = client.post(
        "/api/v1/admin/sync/push",
        content=b"not-a-zip",
        headers={"Content-Type": "application/zip"},
    )
    assert response.status_code == 401


def test_push_endpoint_merges_slave_accounts_into_master(tmp_path: Path) -> None:
    master_settings: Settings = Settings(
        data_dir=tmp_path / "master",
        admin_username="admin",
        admin_password="admin-password",
    )
    build_master(master_settings, "one")
    client: TestClient = TestClient(create_app(master_settings))
    login_response = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin-password"}
    )
    admin_headers: dict[str, str] = {
        "Authorization": f"Bearer {login_response.json()['access_token']}"
    }

    slave_settings: Settings = Settings(
        data_dir=tmp_path / "slave",
        admin_username="admin",
        admin_password="admin-password",
    )
    build_master(slave_settings, "slave")
    with connect(slave_settings) as connection:
        connection.execute(
            "INSERT INTO email_accounts (user_id, provider, primary_address, refresh_token)"
            " VALUES (1, 'gmail', 'slave-only@example.com', 'refresh-slave')"
        )
        connection.execute(
            "INSERT INTO usable_emails (user_id, email_account_id, address)"
            " VALUES (1, 2, 'slave-only-mail@example.com')"
        )

    response = client.post(
        "/api/v1/admin/sync/push",
        content=create_instance_backup(slave_settings),
        headers={**admin_headers, "Content-Type": "application/zip"},
    )

    assert response.status_code == 200
    assert response.json()["error"] == ""
    with connect(master_settings) as connection:
        addresses: list[str] = [
            str(row[0])
            for row in connection.execute(
                "SELECT primary_address FROM email_accounts ORDER BY primary_address"
            )
        ]
        usable_addresses: list[str] = [
            str(row[0])
            for row in connection.execute("SELECT address FROM usable_emails ORDER BY address")
        ]
    assert addresses == [
        "account-one@example.com",
        "account-slave@example.com",
        "slave-only@example.com",
    ]
    assert usable_addresses == [
        "mail-one@example.com",
        "mail-slave@example.com",
        "slave-only-mail@example.com",
    ]


def test_push_endpoint_does_not_overwrite_existing_master_rows(tmp_path: Path) -> None:
    master_settings: Settings = Settings(
        data_dir=tmp_path / "master",
        admin_username="admin",
        admin_password="admin-password",
    )
    build_master(master_settings, "one")
    client: TestClient = TestClient(create_app(master_settings))
    login_response = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin-password"}
    )
    admin_headers: dict[str, str] = {
        "Authorization": f"Bearer {login_response.json()['access_token']}"
    }

    slave_settings: Settings = Settings(
        data_dir=tmp_path / "slave",
        admin_username="admin",
        admin_password="admin-password",
    )
    build_master(slave_settings, "one")
    with connect(slave_settings) as connection:
        connection.execute(
            "UPDATE email_accounts SET remark = 'slave-remark'"
            " WHERE primary_address = 'account-one@example.com'"
        )

    response = client.post(
        "/api/v1/admin/sync/push",
        content=create_instance_backup(slave_settings),
        headers={**admin_headers, "Content-Type": "application/zip"},
    )

    assert response.status_code == 200
    with connect(master_settings) as connection:
        remark: str = str(
            connection.execute(
                "SELECT remark FROM email_accounts"
                " WHERE primary_address = 'account-one@example.com'"
            ).fetchone()[0]
        )
    assert remark == ""


class _SyncPushCaptureHandler(BaseHTTPRequestHandler):
    captured: ClassVar[dict[str, object]] = {}

    def do_POST(self) -> None:
        length: int = int(self.headers.get("Content-Length", "0"))
        body: bytes = self.rfile.read(length)
        type(self).captured = {
            "path": self.path,
            "authorization": self.headers.get("Authorization", ""),
            "content_type": self.headers.get("Content-Type", ""),
            "body": body,
        }
        payload: bytes = json.dumps(
            {"error": "", "tables": {"users": 1, "email_accounts": 1}}
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


def test_push_snapshot_posts_local_archive_to_master(tmp_path: Path) -> None:
    _SyncPushCaptureHandler.captured = {}
    server: ThreadingHTTPServer = ThreadingHTTPServer(("127.0.0.1", 0), _SyncPushCaptureHandler)
    thread: threading.Thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        settings: Settings = Settings(
            data_dir=tmp_path / "slave",
            admin_username="admin",
            admin_password="admin-password",
            sync_url=f"http://127.0.0.1:{server.server_port}",
            sync_token="secret-token",
        )
        report = push_snapshot(settings)

        assert report.error == ""
        assert report.tables == {"users": 1, "email_accounts": 1}
        captured: dict[str, object] = _SyncPushCaptureHandler.captured
        assert captured["path"] == "/api/v1/admin/sync/push"
        assert captured["authorization"] == "Bearer secret-token"
        assert captured["content_type"] == "application/zip"
        assert captured["body"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_run_sync_pulls_then_pushes_and_reports_push_error(monkeypatch, tmp_path: Path) -> None:
    settings: Settings = Settings(data_dir=tmp_path / "node")

    def fake_pull(settings_arg: Settings) -> SyncReport:
        return SyncReport(started_at="s", finished_at="f", tables={"users": 1})

    def fake_push(settings_arg: Settings) -> SyncReport:
        return SyncReport(started_at="s", finished_at="f2", error="push-boom")

    monkeypatch.setattr("hx_email.server.sync.service.pull_snapshot", fake_pull)
    monkeypatch.setattr("hx_email.server.sync.service.push_snapshot", fake_push)

    report = run_sync(settings)

    assert report.tables == {"users": 1}
    assert report.error == "push-boom"
    assert report.push["error"] == "push-boom"
    assert report.finished_at == "f2"


def test_cli_sync_push_only_without_config_exits_nonzero(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HX_EMAIL_DATA_DIR", str(tmp_path / "runtime"))
    monkeypatch.delenv("HX_EMAIL_SYNC_URL", raising=False)
    monkeypatch.delenv("HX_EMAIL_SYNC_TOKEN", raising=False)

    assert main(["sync", "--push-only"]) == 1
