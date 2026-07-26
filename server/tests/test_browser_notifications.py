"""Browser notification polling: cursor init, new-mail feed, per-email/group mute."""

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import connect

API = "/api/v1"


def make_client(tmp_path):
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    client = TestClient(create_app(settings))
    client.__enter__()  # run startup migration
    token = client.post(
        f"{API}/auth/login", json={"username": "admin", "password": "admin"}
    ).json()["access_token"]
    return client, settings, {"Authorization": f"Bearer {token}"}


def insert_message(settings: Settings, user_id: int, usable_email_id: int, subject: str) -> int:
    with connect(settings) as conn:
        cursor = conn.execute(
            "INSERT INTO fetched_messages (user_id, usable_email_id, subject, body, body_hash)"
            " VALUES (?, ?, ?, ?, ?)",
            (user_id, usable_email_id, subject, "body of " + subject, subject),
        )
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)


def create_email(client, headers, address: str) -> int:
    response = client.post(
        f"{API}/usable-emails", json={"address": address, "label": ""}, headers=headers
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_first_poll_initializes_cursor_without_flooding_old_mail(tmp_path):
    client, settings, headers = make_client(tmp_path)
    email_id = create_email(client, headers, "a@example.com")
    insert_message(settings, 1, email_id, "old mail")

    response = client.get(f"{API}/notifications", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["notifications"] == []
    assert body["latest_id"] >= 1


def test_poll_returns_new_mail_with_extracted_code(tmp_path):
    client, settings, headers = make_client(tmp_path)
    email_id = create_email(client, headers, "a@example.com")
    baseline = client.get(f"{API}/notifications", headers=headers).json()["latest_id"]
    insert_message(settings, 1, email_id, "Your verification code is 482913")

    body = client.get(f"{API}/notifications?since_id={baseline}", headers=headers).json()

    assert len(body["notifications"]) == 1
    item = body["notifications"][0]
    assert item["address"] == "a@example.com"
    assert item["verification_code"] == "482913"
    assert body["latest_id"] == item["id"]


def test_muted_email_and_group_are_excluded_but_cursor_advances(tmp_path):
    client, settings, headers = make_client(tmp_path)
    muted_email = create_email(client, headers, "muted@example.com")
    grouped_email = create_email(client, headers, "grouped@example.com")
    noisy_email = create_email(client, headers, "noisy@example.com")

    group_id = client.post(f"{API}/groups", json={"name": "quiet"}, headers=headers).json()["id"]
    client.put(
        f"{API}/usable-emails/{grouped_email}/organize",
        json={"group_id": group_id},
        headers=headers,
    )
    assert client.put(
        f"{API}/usable-emails/{muted_email}/notify", json={"enabled": False}, headers=headers
    ).json() == {"id": muted_email, "notify_enabled": False}
    assert client.put(
        f"{API}/groups/{group_id}/notify", json={"enabled": False}, headers=headers
    ).json() == {"id": group_id, "notify_enabled": False}

    insert_message(settings, 1, muted_email, "muted subject")
    insert_message(settings, 1, grouped_email, "group-muted subject")
    last_id = insert_message(settings, 1, noisy_email, "audible subject")

    body = client.get(f"{API}/notifications?since_id=0", headers=headers).json()

    assert [item["subject"] for item in body["notifications"]] == ["audible subject"]
    assert body["latest_id"] == last_id


def test_mute_state_round_trips_through_email_and_group_listings(tmp_path):
    client, _settings, headers = make_client(tmp_path)
    email_id = create_email(client, headers, "a@example.com")
    group_id = client.post(f"{API}/groups", json={"name": "g"}, headers=headers).json()["id"]

    client.put(f"{API}/usable-emails/{email_id}/notify", json={"enabled": False}, headers=headers)
    client.put(f"{API}/groups/{group_id}/notify", json={"enabled": False}, headers=headers)

    emails = client.get(f"{API}/usable-emails", headers=headers).json()["usable_emails"]
    groups = client.get(f"{API}/groups", headers=headers).json()

    assert emails[0]["notify_enabled"] is False
    assert groups[0]["notify_enabled"] is False


def test_notify_toggle_404_for_unknown_targets(tmp_path):
    client, _settings, headers = make_client(tmp_path)

    email_response = client.put(
        f"{API}/usable-emails/999/notify", json={"enabled": True}, headers=headers
    )
    group_response = client.put(f"{API}/groups/999/notify", json={"enabled": True}, headers=headers)

    assert email_response.status_code == 404
    assert group_response.status_code == 404
