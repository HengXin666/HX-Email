"""Regression tests: login throttling with failure count and exponential backoff."""

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.database import migrate
from hx_email.server.auth import LoginRateLimiter

API = "/api/v1"


def test_rate_limiter_locks_after_consecutive_failures_and_resets_on_success() -> None:
    limiter = LoginRateLimiter()
    for _ in range(4):
        limiter.record_failure("victim", "1.1.1.1")
        assert limiter.acquire("victim", "1.1.1.1") is None
    limiter.record_failure("victim", "1.1.1.1")
    retry_after = limiter.acquire("victim", "1.1.1.1")
    assert retry_after is not None and retry_after >= 1
    limiter.record_success("victim", "1.1.1.1")
    assert limiter.acquire("victim", "1.1.1.1") is None


def test_rate_limiter_locks_username_across_different_ips() -> None:
    limiter = LoginRateLimiter()
    for _ in range(5):
        limiter.record_failure("victim", "1.1.1.1")
    assert limiter.acquire("victim", "2.2.2.2") is not None


def test_rate_limiter_backoff_grows_exponentially(monkeypatch) -> None:
    now = [1000.0]
    monkeypatch.setattr("hx_email.server.auth.time.monotonic", lambda: now[0])
    limiter = LoginRateLimiter()
    for _ in range(5):
        limiter.record_failure("victim", "1.1.1.1")
    first_retry = limiter.acquire("victim", "1.1.1.1")
    assert first_retry is not None

    now[0] += first_retry + 1
    for _ in range(5):
        limiter.record_failure("victim", "1.1.1.1")
    second_retry = limiter.acquire("victim", "1.1.1.1")
    assert second_retry is not None
    assert second_retry > first_retry


def test_login_endpoint_returns_429_after_repeated_failures(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings), client=("203.0.113.7", 1234))

    for _ in range(5):
        response = client.post(
            f"{API}/auth/login",
            json={"username": "nobody", "password": "wrong"},
        )
        assert response.status_code == 401

    locked = client.post(
        f"{API}/auth/login",
        json={"username": "nobody", "password": "wrong"},
    )
    assert locked.status_code == 429
    assert int(locked.headers["Retry-After"]) >= 1


def test_login_success_resets_failure_counter(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    migrate(settings)
    client = TestClient(create_app(settings), client=("203.0.113.8", 1234))

    for _ in range(3):
        assert (
            client.post(
                f"{API}/auth/login",
                json={"username": "admin", "password": "wrong"},
            ).status_code
            == 401
        )
    ok = client.post(
        f"{API}/auth/login",
        json={"username": "admin", "password": "admin"},
    )
    assert ok.status_code == 200
    for _ in range(3):
        assert (
            client.post(
                f"{API}/auth/login",
                json={"username": "admin", "password": "wrong"},
            ).status_code
            == 401
        )
    ok_again = client.post(
        f"{API}/auth/login",
        json={"username": "admin", "password": "admin"},
    )
    assert ok_again.status_code == 200
