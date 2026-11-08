"""Where a webhook subscription delivers, and how a receiver proves a batch is ours.

URL and secret live together, encrypted, in ``router_routes.target_encrypted``
(spec 8.1). The secret is shown once when created or rotated and never read back
through the API. Each batch carries ``X-HX-Router-Signature: sha256=<hex>``, an
HMAC-SHA256 of the exact request body with that secret (spec 6, outbound webhook).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit

from hx_email.config import Settings
from hx_email.security import decrypt_secret, encrypt_secret
from hx_email.server.router.errors import RouteInvalidError

LOGGER: logging.Logger = logging.getLogger("hx_email.push.target")
SECRET_PREFIX: Final[str] = "whsec_"
MAX_URL_LENGTH: Final[int] = 500
SIGNATURE_HEADER: Final[str] = "X-HX-Router-Signature"
DELIVERY_HEADER: Final[str] = "X-HX-Router-Delivery"
SUBSCRIPTION_HEADER: Final[str] = "X-HX-Router-Subscription"


@dataclass(frozen=True)
class WebhookTarget:
    url: str
    secret: str


def check_url(url: str) -> str:
    """Accept an absolute http(s) URL without embedded credentials."""
    value: str = url.strip()
    parts = urlsplit(value)
    if len(value) > MAX_URL_LENGTH or parts.scheme not in ("http", "https") or not parts.hostname:
        raise RouteInvalidError("webhook_url must be an absolute http(s) URL")
    if parts.username or parts.password:
        raise RouteInvalidError("webhook_url must not embed credentials")
    return value


def new_secret() -> str:
    return SECRET_PREFIX + secrets.token_urlsafe(32)


def seal_target(settings: Settings, target: WebhookTarget) -> str:
    plain: str = json.dumps({"url": target.url, "secret": target.secret}, separators=(",", ":"))
    return encrypt_secret(settings, plain)


def open_target(settings: Settings, sealed: str) -> WebhookTarget | None:
    """Decrypt a stored target; a corrupt value reads as "no target" and is logged."""
    try:
        data: object = json.loads(decrypt_secret(settings, sealed))
    except (ValueError, OSError, RuntimeError) as error:
        LOGGER.warning("cannot open webhook target: %s", error)
        return None
    if not isinstance(data, dict):
        return None
    return WebhookTarget(str(data.get("url") or ""), str(data.get("secret") or ""))


def sign(secret: str, body: bytes) -> str:
    digest: str = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(secret: str, body: bytes, header: str) -> bool:
    """What a receiver does; constant-time compare against our signature."""
    return hmac.compare_digest(sign(secret, body), header.strip())
