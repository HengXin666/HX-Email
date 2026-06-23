from fastapi.testclient import TestClient
from hx_email.app import create_app


def test_health_check_reports_server_status():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "hx-email"}
