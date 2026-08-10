from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate

VERIFICATION_BODY = "google-site-verification: google18261d952ce2f02c.html"


def login(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    response.raise_for_status()
    token: str = str(response.json()["access_token"])
    return {"Authorization": f"Bearer {token}"}


def make_settings(tmp_path: Path) -> Settings:
    settings: Settings = Settings(
        data_dir=tmp_path,
        admin_username="admin",
        admin_password="admin-password",
    )
    migrate(settings)
    return settings


def upload(client: TestClient, headers: dict[str, str], filename: str, content: str) -> object:
    return client.post(
        f"/api/v1/admin/google-verification?filename={filename}",
        content=content.encode("utf-8"),
        headers={**headers, "Content-Type": "text/html"},
    )


def test_google_verification_upload_is_admin_only(tmp_path: Path) -> None:
    client = TestClient(create_app(make_settings(tmp_path)))
    admin_headers = login(client, "admin", "admin-password")
    client.put(
        "/api/v1/admin/settings/registration",
        json={"enabled": True},
        headers=admin_headers,
    )
    user_response = client.post(
        "/api/v1/auth/register",
        json={"username": "ordinary", "password": "ordinary-password"},
    )
    user_headers: dict[str, str] = {
        "Authorization": f"Bearer {user_response.json()['access_token']}"
    }

    assert client.get("/api/v1/admin/google-verification", headers=user_headers).status_code == 403
    assert (
        upload(client, user_headers, "google18261d952ce2f02c.html", VERIFICATION_BODY).status_code
        == 403
    )


def test_google_verification_upload_serve_and_delete(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    client = TestClient(create_app(settings))
    headers = login(client, "admin", "admin-password")

    # Uploading replaces any previous file and only keeps one active.
    first = upload(client, headers, "google18261d952ce2f02c.html", VERIFICATION_BODY)
    assert first.status_code == 201
    assert first.json() == {
        "filename": "google18261d952ce2f02c.html",
        "url": "/google18261d952ce2f02c.html",
    }

    second_name = "googleaabbccddeeff00.html"
    second = upload(
        client,
        headers,
        second_name,
        f"google-site-verification: {second_name}",
    )
    assert second.status_code == 201

    listed = client.get("/api/v1/admin/google-verification", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["files"] == [{"filename": second_name, "url": f"/{second_name}"}]

    # The file is served publicly at the site root without credentials.
    served = client.get(f"/{second_name}")
    assert served.status_code == 200
    assert served.headers["content-type"] == "text/html; charset=utf-8"
    assert served.text == f"google-site-verification: {second_name}"

    # The replaced file is gone.
    assert client.get("/google18261d952ce2f02c.html").status_code == 404

    deleted = client.delete(f"/api/v1/admin/google-verification/{second_name}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(f"/{second_name}").status_code == 404


def test_google_verification_rejects_invalid_files(tmp_path: Path) -> None:
    client = TestClient(create_app(make_settings(tmp_path)))
    headers = login(client, "admin", "admin-password")

    bad_name = upload(client, headers, "verify-me.html", VERIFICATION_BODY)
    assert bad_name.status_code == 422

    bad_content = upload(client, headers, "google18261d952ce2f02c.html", "<html>hello</html>")
    assert bad_content.status_code == 422

    # Non-verification single-segment paths must stay 404.
    assert client.get("/login").status_code == 404
    assert client.get("/home").status_code == 404
