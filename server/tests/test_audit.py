import json

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate


def authenticated_admin(tmp_path) -> tuple[TestClient, dict[str, str]]:
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
    return client, {"Authorization": f"Bearer {session['access_token']}"}


def test_mutation_request_is_written_to_audit_log(tmp_path) -> None:
    client, headers = authenticated_admin(tmp_path)

    created = client.post(
        "/api/v1/groups",
        json={"name": "Ops", "color": "#58a6ff"},
        headers=headers,
    )
    audit = client.get("/api/v1/audit-logs?resource_type=group", headers=headers)

    assert created.status_code == 201
    assert audit.status_code == 200
    body = audit.json()
    assert body["total"] == 1
    log = body["logs"][0]
    detail = json.loads(log["detail"])
    assert log["action"] == "create"
    assert log["resource_type"] == "group"
    assert log["user_id"] == 1
    assert detail["route"] == "/groups"
    assert detail["status_code"] == 201
    assert detail["source"] == "internal"


def test_audit_query_does_not_create_audit_noise(tmp_path) -> None:
    client, headers = authenticated_admin(tmp_path)

    first = client.get("/api/v1/audit-logs", headers=headers).json()
    second = client.get("/api/v1/audit-logs", headers=headers).json()

    assert second["total"] == first["total"]


def test_failed_mutation_is_not_recorded_as_successful_action(tmp_path) -> None:
    client, headers = authenticated_admin(tmp_path)

    failed = client.delete("/api/v1/groups/9999", headers=headers)
    audit = client.get(
        "/api/v1/audit-logs?action=delete&resource_type=group",
        headers=headers,
    ).json()

    assert failed.status_code == 404
    assert audit["total"] == 0
