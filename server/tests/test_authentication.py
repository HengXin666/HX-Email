from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import ENV_FILE_PATH, REPOSITORY_ROOT, Settings
from hx_email.database import migrate


def test_settings_env_file_is_bound_to_repository_root() -> None:
    assert ENV_FILE_PATH == REPOSITORY_ROOT / ".env"
    assert ENV_FILE_PATH.is_absolute()


def test_admin_can_log_in_after_database_initializes_from_environment(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        admin_username="owner",
        admin_password="secret-pass",
    )
    migrate(settings)
    client = TestClient(create_app(settings))

    response = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "secret-pass"},
    )

    assert response.status_code == 200
    session = response.json()
    assert session["user"]["username"] == "owner"
    assert session["user"]["is_admin"] is True
    assert session["access_token"]


def test_registration_is_rejected_until_admin_enables_it(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        admin_username="owner",
        admin_password="secret-pass",
    )
    migrate(settings)
    client = TestClient(create_app(settings))

    closed_response = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "password": "alice-pass"},
    )

    assert closed_response.status_code == 403

    admin_session = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "secret-pass"},
    ).json()
    toggle_response = client.put(
        "/api/v1/admin/settings/registration",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {admin_session['access_token']}"},
    )
    open_response = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "password": "alice-pass"},
    )

    assert toggle_response.status_code == 200
    assert toggle_response.json() == {"registration_enabled": True}
    assert open_response.status_code == 201
    assert open_response.json()["user"]["username"] == "alice"
    assert open_response.json()["access_token"]


def test_admin_can_update_own_credentials_and_log_out(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        admin_username="owner",
        admin_password="secret-pass",
    )
    migrate(settings)
    client = TestClient(create_app(settings))
    session = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "secret-pass"},
    ).json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}

    update_response = client.put(
        "/api/v1/auth/me/credentials",
        json={"username": "renamed-owner", "password": "new-secret-pass"},
        headers=headers,
    )
    old_login = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "secret-pass"},
    )
    new_login = client.post(
        "/api/v1/auth/login",
        json={"username": "renamed-owner", "password": "new-secret-pass"},
    )
    logout_response = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {new_login.json()['access_token']}"},
    )
    rejected_after_logout = client.put(
        "/api/v1/admin/settings/registration",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {new_login.json()['access_token']}"},
    )

    assert update_response.status_code == 200
    assert update_response.json()["user"]["username"] == "renamed-owner"
    assert old_login.status_code == 401
    assert new_login.status_code == 200
    assert logout_response.status_code == 204
    assert rejected_after_logout.status_code == 401


def test_expired_session_token_is_rejected_and_purged(tmp_path) -> None:
    from datetime import UTC, datetime, timedelta

    from hx_email.database import connect

    settings = Settings(
        data_dir=tmp_path,
        admin_username="owner",
        admin_password="secret-pass",
    )
    migrate(settings)
    client = TestClient(create_app(settings))
    session = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "secret-pass"},
    ).json()
    token: str = session["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/bootstrap", headers=headers).status_code == 200

    past: str = (
        (datetime.now(UTC) - timedelta(minutes=1))
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
    with connect(settings) as connection:
        connection.execute("UPDATE sessions SET expires_at = ? WHERE token = ?", (past, token))

    rejected = client.get("/api/v1/bootstrap", headers=headers)
    assert rejected.status_code == 401

    with connect(settings) as connection:
        remaining = connection.execute(
            "SELECT COUNT(*) AS n FROM sessions WHERE token = ?", (token,)
        ).fetchone()
    assert remaining["n"] == 0


def test_session_expiry_column_present_and_future_for_new_logins(tmp_path) -> None:
    from datetime import UTC, datetime

    from hx_email.database import connect

    settings = Settings(
        data_dir=tmp_path,
        admin_username="owner",
        admin_password="secret-pass",
    )
    migrate(settings)
    client = TestClient(create_app(settings))
    session = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "secret-pass"},
    ).json()
    token: str = session["access_token"]

    with connect(settings) as connection:
        row = connection.execute(
            "SELECT expires_at FROM sessions WHERE token = ?", (token,)
        ).fetchone()
    expires_at: str = row["expires_at"]
    assert expires_at
    parsed: datetime = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    assert parsed > datetime.now(UTC)
    assert (parsed - datetime.now(UTC)).days >= 29
