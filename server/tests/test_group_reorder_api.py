"""API-level tests for group drag-reorder and batch-delete endpoints."""

from pathlib import Path

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate


def _client(tmp_path: Path) -> tuple[TestClient, dict[str, str]]:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings))
    session = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "admin"}
    ).json()
    return client, {"Authorization": f"Bearer {session['access_token']}"}


def _create_group(client: TestClient, headers: dict[str, str], name: str) -> int:
    response = client.post(
        "/api/v1/groups", json={"name": name, "color": "#58a6ff"}, headers=headers
    )
    assert response.status_code == 201
    return response.json()["id"]


def _group_ids(client: TestClient, headers: dict[str, str]) -> list[int]:
    response = client.get("/api/v1/groups", headers=headers)
    assert response.status_code == 200
    return [group["id"] for group in response.json()]


def test_reorder_groups_endpoint_persists_order(tmp_path: Path) -> None:
    client, headers = _client(tmp_path)
    first = _create_group(client, headers, "甲")
    second = _create_group(client, headers, "乙")
    third = _create_group(client, headers, "丙")
    assert _group_ids(client, headers) == [first, second, third]

    response = client.post(
        "/api/v1/groups/reorder", json={"group_ids": [third, first, second]}, headers=headers
    )
    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert _group_ids(client, headers) == [third, first, second]


def test_reorder_groups_endpoint_rejects_incomplete_ids(tmp_path: Path) -> None:
    client, headers = _client(tmp_path)
    first = _create_group(client, headers, "甲")
    _create_group(client, headers, "乙")
    response = client.post("/api/v1/groups/reorder", json={"group_ids": [first]}, headers=headers)
    assert response.status_code == 400


def test_reorder_groups_requires_auth(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    response = client.post("/api/v1/groups/reorder", json={"group_ids": []})
    assert response.status_code == 401


def test_batch_delete_groups_endpoint(tmp_path: Path) -> None:
    client, headers = _client(tmp_path)
    first = _create_group(client, headers, "甲")
    second = _create_group(client, headers, "乙")
    third = _create_group(client, headers, "丙")

    response = client.post(
        "/api/v1/groups/batch-delete", json={"group_ids": [first, third]}, headers=headers
    )
    assert response.status_code == 200
    assert response.json() == {"deleted": 2}
    assert _group_ids(client, headers) == [second]


def test_batch_delete_groups_is_scoped_to_owner(tmp_path: Path) -> None:
    client, headers = _client(tmp_path)
    client.put(
        "/api/v1/admin/settings/registration",
        json={"enabled": True},
        headers=headers,
    )
    other_session = client.post(
        "/api/v1/auth/register", json={"username": "other", "password": "other-pass"}
    ).json()
    other_headers = {"Authorization": f"Bearer {other_session['access_token']}"}
    admin_group = _create_group(client, headers, "管理员组")
    other_group = _create_group(client, other_headers, "他人组")

    response = client.post(
        "/api/v1/groups/batch-delete",
        json={"group_ids": [admin_group, other_group]},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json() == {"deleted": 1}
    assert _group_ids(client, headers) == []
    assert _group_ids(client, other_headers) == [other_group]
