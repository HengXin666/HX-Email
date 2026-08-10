"""SSRF guard for user-supplied proxy targets.

Validates that proxy hosts are not private, link-local, reserved, or
metadata addresses (RFC1918 / 169.254.0.0/16 / 127.0.0.0/8 / 0.0.0.0/8 etc.).
Hostnames are resolved and every resolved address must be public.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

BLOCKED_IPV4_NETWORKS: tuple[ipaddress.IPv4Network, ...] = (
    ipaddress.IPv4Network("0.0.0.0/8"),
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("100.64.0.0/10"),
    ipaddress.IPv4Network("127.0.0.0/8"),
    ipaddress.IPv4Network("169.254.0.0/16"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.0.0.0/24"),
    ipaddress.IPv4Network("192.0.2.0/24"),
    ipaddress.IPv4Network("192.168.0.0/16"),
    ipaddress.IPv4Network("198.18.0.0/15"),
    ipaddress.IPv4Network("198.51.100.0/24"),
    ipaddress.IPv4Network("203.0.113.0/24"),
    ipaddress.IPv4Network("224.0.0.0/4"),
    ipaddress.IPv4Network("240.0.0.0/4"),
)

BLOCKED_IPV6_NETWORKS: tuple[ipaddress.IPv6Network, ...] = (
    ipaddress.IPv6Network("::/128"),
    ipaddress.IPv6Network("::1/128"),
    ipaddress.IPv6Network("::ffff:0:0/96"),
    ipaddress.IPv6Network("64:ff9b::/96"),
    ipaddress.IPv6Network("2001:db8::/32"),
    ipaddress.IPv6Network("fc00::/7"),
    ipaddress.IPv6Network("fe80::/10"),
    ipaddress.IPv6Network("ff00::/8"),
)


def _is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv4Address):
        return any(ip in network for network in BLOCKED_IPV4_NETWORKS)
    if ip.ipv4_mapped is not None and any(
        ip.ipv4_mapped in network for network in BLOCKED_IPV4_NETWORKS
    ):
        return True
    return any(ip in network for network in BLOCKED_IPV6_NETWORKS)


def _parse_proxy_url(proxy_url: str) -> tuple[str, int]:
    value: str = proxy_url.strip()
    parsed = urlsplit(value if "://" in value else f"//{value}")
    host: str | None = parsed.hostname
    if not host:
        raise ValueError("代理 URL 缺少主机名")
    try:
        port: int = parsed.port or 8080
    except ValueError as error:
        raise ValueError("代理 URL 端口无效") from error
    return host, port


def validate_proxy_host(host: str) -> str:
    """Validate a proxy host; returns the canonical hostname or raises ValueError."""
    candidate: str = host.strip()
    if not candidate:
        raise ValueError("代理地址为空")
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address | None
    try:
        ip = ipaddress.ip_address(candidate)
    except ValueError:
        ip = None
    if ip is not None and _is_blocked(ip):
        raise ValueError("代理地址不允许(私网/保留地址)")
    if ip is None:
        try:
            addresses: list[str] = [str(info[4][0]) for info in socket.getaddrinfo(candidate, None)]
        except socket.gaierror as error:
            raise ValueError(f"代理主机解析失败: {error}") from error
        for address in addresses:
            if _is_blocked(ipaddress.ip_address(address)):
                raise ValueError("代理地址不允许(解析到私网/保留地址)")
    return candidate


def resolve_proxy_host(host: str) -> str:
    """Resolve a proxy host once, validate every address, and return a pinned IP.

    Callers must connect to the returned IP literal instead of re-resolving the
    hostname, which would otherwise reopen a DNS-rebinding TOCTOU window.
    """
    candidate: str = host.strip()
    if not candidate:
        raise ValueError("代理地址为空")
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address | None
    try:
        ip = ipaddress.ip_address(candidate)
    except ValueError:
        ip = None
    if ip is not None:
        if _is_blocked(ip):
            raise ValueError("代理地址不允许(私网/保留地址)")
        return candidate
    try:
        infos = socket.getaddrinfo(candidate, None)
    except socket.gaierror as error:
        raise ValueError(f"代理主机解析失败: {error}") from error
    pinned: str | None = None
    for info in infos:
        address: str | int = info[4][0]
        if not isinstance(address, str):
            continue
        if _is_blocked(ipaddress.ip_address(address)):
            raise ValueError("代理地址不允许(解析到私网/保留地址)")
        if pinned is None:
            pinned = address
    if pinned is None:
        raise ValueError("代理主机解析失败: 无可用地址")
    return pinned


def validate_proxy_endpoint(proxy_url: str) -> tuple[str, int]:
    """Validate a user-supplied proxy URL; returns (host, port) or raises ValueError."""
    host, port = _parse_proxy_url(proxy_url)
    return validate_proxy_host(host), port


def resolve_proxy_endpoint(proxy_url: str) -> tuple[str, int]:
    """Resolve and validate a user-supplied proxy URL; returns a pinned (ip, port)."""
    host, port = _parse_proxy_url(proxy_url)
    return resolve_proxy_host(host), port
