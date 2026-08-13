"""SSRF guard for user-supplied proxy and mail-server targets.

Proxy targets (group ``proxy_url``, ``/groups/proxy-test``, IMAP tunneling) are
restricted to a whitelist: loopback (``127.0.0.0/8``, ``::1``), the Docker
gateway hostnames (``host.docker.internal`` / ``gateway.docker.internal``), and
public addresses. RFC1918/ULA private ranges, link-local, cloud-metadata,
multicast, broadcast, reserved and documentation ranges are all blocked. This
matches the documented deployment (host-local ``http://127.0.0.1:7890`` proxies
and the Docker bridge gateway) while closing the regression where any logged-in
user could probe arbitrary internal host:port.

Server-side outbound probes (plugin ``api_base_url``) use the stricter
``resolve_public_host``, which only allows public addresses. Hostnames are
resolved and every resolved address must pass the same check; IPv4-mapped IPv6
is judged by its embedded IPv4 address.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

LOOPBACK_IPV4: ipaddress.IPv4Network = ipaddress.IPv4Network("127.0.0.0/8")
LOOPBACK_IPV6: ipaddress.IPv6Network = ipaddress.IPv6Network("::1/128")

PRIVATE_IPV4_NETWORKS: tuple[ipaddress.IPv4Network, ...] = (
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
)

PRIVATE_IPV6_NETWORKS: tuple[ipaddress.IPv6Network, ...] = (ipaddress.IPv6Network("fc00::/7"),)

BLOCKED_IPV4_NETWORKS: tuple[ipaddress.IPv4Network, ...] = (
    ipaddress.IPv4Network("0.0.0.0/8"),
    ipaddress.IPv4Network("100.64.0.0/10"),
    ipaddress.IPv4Network("169.254.0.0/16"),
    ipaddress.IPv4Network("192.0.0.0/24"),
    ipaddress.IPv4Network("192.0.2.0/24"),
    ipaddress.IPv4Network("198.18.0.0/15"),
    ipaddress.IPv4Network("198.51.100.0/24"),
    ipaddress.IPv4Network("203.0.113.0/24"),
    ipaddress.IPv4Network("224.0.0.0/4"),
    ipaddress.IPv4Network("240.0.0.0/4"),
)

BLOCKED_IPV6_NETWORKS: tuple[ipaddress.IPv6Network, ...] = (
    ipaddress.IPv6Network("::/128"),
    ipaddress.IPv6Network("::ffff:0:0/96"),
    ipaddress.IPv6Network("64:ff9b::/96"),
    ipaddress.IPv6Network("2001::/32"),
    ipaddress.IPv6Network("2002::/16"),
    ipaddress.IPv6Network("2001:db8::/32"),
    ipaddress.IPv6Network("fe80::/10"),
    ipaddress.IPv6Network("ff00::/8"),
)

GLOBAL_UNICAST_IPV6: ipaddress.IPv6Network = ipaddress.IPv6Network("2000::/3")

DOCKER_HOST_NAMES: frozenset[str] = frozenset({"host.docker.internal", "gateway.docker.internal"})


def _is_loopback(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv4Address):
        return ip in LOOPBACK_IPV4
    if ip.ipv4_mapped is not None:
        return ip.ipv4_mapped in LOOPBACK_IPV4
    return ip in LOOPBACK_IPV6


def _is_private(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv4Address):
        return any(ip in network for network in PRIVATE_IPV4_NETWORKS)
    if ip.ipv4_mapped is not None:
        return any(ip.ipv4_mapped in network for network in PRIVATE_IPV4_NETWORKS)
    return any(ip in network for network in PRIVATE_IPV6_NETWORKS)


def _is_hard_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Metadata/link-local/multicast/broadcast/reserved/documentation ranges."""
    if isinstance(ip, ipaddress.IPv4Address):
        return any(ip in network for network in BLOCKED_IPV4_NETWORKS)
    if ip.ipv4_mapped is not None:
        return any(ip.ipv4_mapped in network for network in BLOCKED_IPV4_NETWORKS)
    if ip not in GLOBAL_UNICAST_IPV6:
        return True
    return any(ip in network for network in BLOCKED_IPV6_NETWORKS)


def _is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Proxy-guard check: loopback is allowed, private ranges are blocked."""
    if _is_loopback(ip):
        return False
    if _is_private(ip):
        return True
    return _is_hard_blocked(ip)


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Public-only check: loopback and private ranges are rejected too."""
    return not _is_loopback(ip) and not _is_private(ip) and not _is_hard_blocked(ip)


def _normalize_host(host: str) -> str:
    candidate: str = host.strip()
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    return candidate


def _resolve_addresses(candidate: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(candidate, None)
    except socket.gaierror as error:
        raise ValueError(f"代理主机解析失败: {error}") from error
    return [str(info[4][0]) for info in infos]


def _proxy_address_allowed(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address, docker_host: bool
) -> bool:
    if docker_host:
        return not _is_hard_blocked(ip)
    return not _is_blocked(ip)


def validate_proxy_host(host: str) -> str:
    """Validate a proxy host; returns the canonical hostname or raises ValueError."""
    candidate: str = _normalize_host(host)
    if not candidate:
        raise ValueError("代理地址为空")
    docker_host: bool = candidate.lower() in DOCKER_HOST_NAMES
    try:
        ip: ipaddress.IPv4Address | ipaddress.IPv6Address | None = ipaddress.ip_address(candidate)
    except ValueError:
        ip = None
    if ip is not None:
        if _is_blocked(ip):
            raise ValueError("代理地址不允许(私网/保留地址)")
        return candidate
    for address in _resolve_addresses(candidate):
        if not _proxy_address_allowed(ipaddress.ip_address(address), docker_host):
            raise ValueError("代理地址不允许(解析到私网/保留地址)")
    return candidate


def resolve_proxy_host(host: str) -> str:
    """Resolve a proxy host once, validate every address, and return a pinned IP.

    Callers must connect to the returned IP literal instead of re-resolving the
    hostname, which would otherwise reopen a DNS-rebinding TOCTOU window.
    """
    candidate: str = _normalize_host(host)
    if not candidate:
        raise ValueError("代理地址为空")
    docker_host: bool = candidate.lower() in DOCKER_HOST_NAMES
    try:
        ip: ipaddress.IPv4Address | ipaddress.IPv6Address | None = ipaddress.ip_address(candidate)
    except ValueError:
        ip = None
    if ip is not None:
        if _is_blocked(ip):
            raise ValueError("代理地址不允许(私网/保留地址)")
        return candidate
    pinned: str | None = None
    for address in _resolve_addresses(candidate):
        if not _proxy_address_allowed(ipaddress.ip_address(address), docker_host):
            raise ValueError("代理地址不允许(解析到私网/保留地址)")
        if pinned is None:
            pinned = address
    if pinned is None:
        raise ValueError("代理主机解析失败: 无可用地址")
    return pinned


def resolve_public_host(host: str) -> str:
    """Resolve a host once and require every address to be public.

    Used for server-side outbound probes (plugin ``api_base_url``): loopback,
    private/RFC1918/ULA, link-local, metadata, reserved and documentation
    addresses are all rejected. Callers must connect to the returned IP literal
    instead of re-resolving the hostname (DNS-rebinding TOCTOU).
    """
    candidate: str = _normalize_host(host)
    if not candidate:
        raise ValueError("主机地址为空")
    try:
        ip: ipaddress.IPv4Address | ipaddress.IPv6Address | None = ipaddress.ip_address(candidate)
    except ValueError:
        ip = None
    if ip is not None:
        if not _is_public(ip):
            raise ValueError("仅允许公网地址")
        return candidate
    pinned: str | None = None
    for address in _resolve_addresses(candidate):
        if not _is_public(ipaddress.ip_address(address)):
            raise ValueError("仅允许公网地址(解析到非公网地址)")
        if pinned is None:
            pinned = address
    if pinned is None:
        raise ValueError("主机解析失败: 无可用地址")
    return pinned


def validate_proxy_endpoint(proxy_url: str) -> tuple[str, int]:
    """Validate a user-supplied proxy URL; returns (host, port) or raises ValueError."""
    host, port = _parse_proxy_url(proxy_url)
    return validate_proxy_host(host), port


def resolve_proxy_endpoint(proxy_url: str) -> tuple[str, int]:
    """Resolve and validate a user-supplied proxy URL; returns a pinned (ip, port)."""
    host, port = _parse_proxy_url(proxy_url)
    return resolve_proxy_host(host), port


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
