"""Shared pytest fixtures for the server test suite."""

import socket
from collections.abc import Callable
from typing import Any

import pytest
from hx_email.server.mail.imap.impl.address_guard import set_private_proxy_policy

# Trusted provider-default IMAP hosts are hardcoded application constants.
# The SSRF guard validates them by resolving DNS at account creation/import
# time; sandboxed/CI environments may intercept DNS and resolve them into the
# RFC 2544 benchmarking range (198.18.0.0/15), which the guard correctly
# blocks. Stub these constants to a public literal IP so account/import tests
# stay hermetic and environment-independent.
PROVIDER_MAIL_HOSTS: frozenset[str] = frozenset(
    {
        "imap.gmail.com",
        "imap.qq.com",
        "imap.aliyun.com",
        "imap.163.com",
        "imap.126.com",
        "imap.mail.yahoo.com",
        "outlook.live.com",
    }
)
PUBLIC_STUB_IP: str = "8.8.8.8"


@pytest.fixture(autouse=True)
def stub_provider_mail_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve provider-default mail hosts to a public IP without real DNS."""

    real_getaddrinfo: Callable[..., list[tuple[Any, ...]]] = socket.getaddrinfo

    def stub_getaddrinfo(
        host: str | bytes | None,
        port: int | str | None,
        *args: Any,
        **kwargs: Any,
    ) -> list[tuple[Any, ...]]:
        if isinstance(host, str) and host.lower() in PROVIDER_MAIL_HOSTS:
            resolved_port: int = port if isinstance(port, int) and port > 0 else 993
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_STUB_IP, resolved_port))]
        return real_getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", stub_getaddrinfo)


@pytest.fixture(autouse=True)
def reset_proxy_policy() -> None:
    """Restore the default (relaxed) SSRF policy after each test.

    Tests that exercise strict mode flip the module-level policy via
    set_private_proxy_policy / Settings(allow_private_proxy=False); this
    fixture guarantees no policy leaks into later tests.
    """
    yield
    set_private_proxy_policy(True)
