from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate


def test_health_check_reports_server_status():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "hx-email"}


def test_startup_migrates_database_before_api_requests(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin"},
        )

    assert response.status_code == 200
    assert response.json()["user"]["username"] == "admin"


def test_diagnostics_requires_admin_and_hides_database_path(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))

    admin_session = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin"},
    ).json()
    client.put(
        "/api/v1/admin/settings/registration",
        json={"enabled": True},
        headers={"Authorization": f"Bearer {admin_session['access_token']}"},
    )
    user_session = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "password": "alice-pass"},
    ).json()

    user_response = client.get(
        "/api/v1/system/diagnostics",
        headers={"Authorization": f"Bearer {user_session['access_token']}"},
    )
    admin_response = client.get(
        "/api/v1/system/diagnostics",
        headers={"Authorization": f"Bearer {admin_session['access_token']}"},
    )

    assert user_response.status_code == 403
    assert admin_response.status_code == 200
    assert "database_path" not in admin_response.json()
    assert "database_size_bytes" in admin_response.json()
