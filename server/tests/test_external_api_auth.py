"""External API auth contract: X-API-Key primary, Authorization compat, RFC-style 401s."""

from fastapi.testclient import TestClient
from hx_email.app import create_app
from hx_email.config import Settings
from hx_email.server.settings_service import set_setting


def make_client(tmp_path) -> TestClient:
    settings = Settings(data_dir=tmp_path, admin_username="admin", admin_password="admin")
    client = TestClient(create_app(settings))
    client.__enter__()  # run startup (migrate) so settings table exists
    set_setting(settings, "external_api_key", "test-key-123")
    return client


def test_external_api_accepts_standard_x_api_key_header(tmp_path):
    client = make_client(tmp_path)

    response = client.get("/api/external/health", headers={"X-API-Key": "test-key-123"})

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_external_api_keeps_authorization_header_compatibility(tmp_path):
    client = make_client(tmp_path)

    raw = client.get("/api/external/health", headers={"Authorization": "test-key-123"})
    bearer = client.get("/api/external/health", headers={"Authorization": "Bearer test-key-123"})

    assert raw.status_code == 200
    assert bearer.status_code == 200


def test_external_api_rejects_missing_or_invalid_key_with_www_authenticate(tmp_path):
    client = make_client(tmp_path)

    missing = client.get("/api/external/health")
    invalid = client.get("/api/external/health", headers={"X-API-Key": "wrong"})

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert missing.headers["WWW-Authenticate"] == "ApiKey"
    assert invalid.headers["WWW-Authenticate"] == "ApiKey"


def test_business_api_401_carries_www_authenticate_bearer(tmp_path):
    client = make_client(tmp_path)

    response = client.get("/api/v1/usable-emails")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_openapi_declares_security_schemes_and_hides_raw_auth_params(tmp_path):
    client = make_client(tmp_path)

    spec = client.get("/openapi.json").json()

    schemes = spec["components"]["securitySchemes"]
    assert schemes["BearerAuth"]["scheme"] == "bearer"
    assert schemes["ApiKeyAuth"]["name"] == "X-API-Key"
    assert spec["paths"]["/api/v1/usable-emails"]["get"]["security"] == [{"BearerAuth": []}]
    assert spec["paths"]["/api/external/health"]["get"]["security"] == [{"ApiKeyAuth": []}]
    assert spec["paths"]["/api/v1/auth/login"]["post"].get("security") is None
    for path_item in spec["paths"].values():
        for operation in path_item.values():
            for parameter in operation.get("parameters", []):
                assert str(parameter.get("name", "")).lower() not in {
                    "authorization",
                    "x-api-key",
                }
