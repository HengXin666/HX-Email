import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from threading import Lock
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

import requests


@dataclass(frozen=True)
class OAuthConfig:
    client_id: str
    redirect_uri: str
    scope: str
    tenant: str
    prompt_consent: bool


FLOW_STORE: dict[str, dict[str, object]] = {}
FLOW_LOCK: Lock = Lock()
FLOW_TTL_SECONDS: int = 20 * 60
OIDC_SCOPES: frozenset[str] = frozenset({"openid", "profile", "email", "offline_access"})


def prepare_oauth(config: OAuthConfig) -> dict[str, str]:
    scope: str = normalize_scope(config.scope)
    validate_scope(scope)
    verifier, challenge = generate_pkce()
    state: str = secrets.token_urlsafe(24)
    tenant: str = config.tenant.strip() or "consumers"
    with FLOW_LOCK:
        prune_expired()
        FLOW_STORE[state] = {
            "created_at": time.time(),
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "scope": scope,
            "tenant": tenant,
            "verifier": verifier,
        }
    params: dict[str, str] = {
        "client_id": config.client_id,
        "response_type": "code",
        "redirect_uri": config.redirect_uri,
        "scope": scope,
        "response_mode": "query",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    if config.prompt_consent:
        params["prompt"] = "consent"
    return {
        "authorization_url": (
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?{urlencode(params)}"
        ),
        "state": state,
        "scope": scope,
    }


def exchange_code(code: str, state: str) -> dict[str, object]:
    flow: dict[str, object] | None = pop_flow(state)
    if flow is None:
        raise ValueError("OAuth state is missing or expired")
    tenant: str = str(flow["tenant"])
    payload: dict[str, str] = {
        "client_id": str(flow["client_id"]),
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": str(flow["redirect_uri"]),
        "code_verifier": str(flow["verifier"]),
        "scope": str(flow["scope"]),
    }
    body: bytes = urlencode(payload).encode()
    request = Request(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        token_data = json.loads(response.read().decode("utf-8"))
    return {
        "client_id": flow["client_id"],
        "refresh_token": token_data.get("refresh_token", ""),
        "access_token": token_data.get("access_token", ""),
        "expires_in": token_data.get("expires_in", 0),
        "token_type": token_data.get("token_type", "Bearer"),
        "granted_scope": token_data.get("scope", ""),
        "requested_scope": flow["scope"],
    }


def parse_callback_url(callback_url: str) -> tuple[str, str]:
    parsed = urlparse(callback_url)
    query = parse_qs(parsed.query)
    code = (query.get("code") or [""])[0]
    state = (query.get("state") or [""])[0]
    if not code:
        raise ValueError("Callback URL does not contain code")
    if not state:
        raise ValueError("Callback URL does not contain state")
    return code, state


def peek_flow(state: str) -> dict[str, object] | None:
    with FLOW_LOCK:
        prune_expired()
        flow = FLOW_STORE.get(state)
    return dict(flow) if flow is not None else None


def generate_pkce() -> tuple[str, str]:
    verifier: str = secrets.token_urlsafe(64)
    digest: bytes = hashlib.sha256(verifier.encode()).digest()
    challenge: str = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def normalize_scope(scope_value: str) -> str:
    scopes: set[str] = set(scope_value.strip().split())
    scopes.add("offline_access")
    return " ".join(sorted(scopes))


def validate_scope(scope: str) -> None:
    scopes: list[str] = scope.split()
    api_scopes: list[str] = [item for item in scopes if item not in OIDC_SCOPES]
    if not api_scopes:
        raise ValueError("At least one Microsoft API scope is required")
    has_default: bool = any(item.endswith("/.default") for item in api_scopes)
    has_named: bool = any(not item.endswith("/.default") for item in api_scopes)
    if has_default and has_named:
        raise ValueError(".default scopes cannot be mixed with named scopes")
    resources: set[str] = {scope_resource(item) for item in api_scopes if scope_resource(item)}
    if len(resources) > 1:
        raise ValueError("Only one Microsoft resource can be requested at a time")


def scope_resource(scope: str) -> str:
    if not scope.startswith("https://"):
        return ""
    parts: list[str] = scope.split("/")
    return "/".join(parts[:3]) if len(parts) >= 4 else ""


def pop_flow(state: str) -> dict[str, object] | None:
    with FLOW_LOCK:
        prune_expired()
        flow = FLOW_STORE.pop(state, None)
    return dict(flow) if flow is not None else None


def prune_expired() -> None:
    now: float = time.time()
    expired: list[str] = [
        key
        for key, value in FLOW_STORE.items()
        if now - created_at_seconds(value.get("created_at")) > FLOW_TTL_SECONDS
    ]
    for key in expired:
        del FLOW_STORE[key]


def created_at_seconds(value: object) -> float:
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def try_refresh_oauth_token(
    client_id: str,
    refresh_token: str,
    tenant: str = "consumers",
    timeout: int = 15,
    proxy_url: str = "",
) -> dict[str, object]:
    """Attempt to refresh a Microsoft OAuth2 token.

    Returns a dict with keys: success (bool), message (str), error_detail (str).
    """
    if not client_id or not refresh_token:
        return {
            "success": False,
            "message": "Missing client_id or refresh_token",
            "error_detail": "missing_credentials",
        }

    token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    try:
        response = requests.post(
            token_url,
            data={
                "client_id": client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=timeout,
            proxies=proxies,
        )
        if response.status_code != 200:
            return {
                "success": False,
                "message": "Token refresh failed",
                "error_detail": response.text,
            }
        response_data: dict[str, object] = response.json()
        if "access_token" in response_data:
            return {
                "success": True,
                "message": "Token refreshed successfully",
                "error_detail": "",
                "access_token": str(response_data.get("access_token", "")),
                "refresh_token": str(response_data.get("refresh_token", "")),
            }
        return {
            "success": False,
            "message": "Token refresh returned unexpected response",
            "error_detail": str(response_data),
        }
    except requests.RequestException as exc:
        return {
            "success": False,
            "message": "Network error during token refresh",
            "error_detail": str(exc),
        }
    except Exception as exc:
        return {
            "success": False,
            "message": "Unexpected error during token refresh",
            "error_detail": str(exc),
        }
