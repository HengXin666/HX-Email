from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings


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
