"""Workspace proxy connectivity probe (backing the group proxy-test endpoint)."""

from __future__ import annotations

import contextlib
import socket
import time

from pydantic import BaseModel

from hx_email.server.mail.imap.impl.address_guard import resolve_proxy_endpoint

TEST_TARGET_HOST: str = "outlook.office365.com"
TEST_TARGET_PORT: int = 993
TEST_TIMEOUT: int = 10


class ProxyTestRequest(BaseModel):
    proxy_url: str


def test_proxy_connect(proxy_url: str) -> dict[str, object]:
    """Test proxy connectivity by sending HTTP CONNECT to a known target."""
    if not proxy_url:
        return {"success": False, "latency_ms": 0, "message": "代理地址为空"}

    try:
        proxy_host, proxy_port = resolve_proxy_endpoint(proxy_url)
    except ValueError as error:
        return {"success": False, "latency_ms": 0, "message": str(error)}
    start: float = time.monotonic()

    try:
        sock: socket.socket = socket.create_connection(
            (proxy_host, proxy_port), timeout=TEST_TIMEOUT
        )
    except OSError as exc:
        latency: float = (time.monotonic() - start) * 1000
        return {
            "success": False,
            "latency_ms": round(latency, 1),
            "message": f"无法连接到代理服务器 {proxy_host}:{proxy_port} — {exc}",
        }

    try:
        connect_cmd: str = (
            f"CONNECT {TEST_TARGET_HOST}:{TEST_TARGET_PORT} HTTP/1.1\r\n"
            f"Host: {TEST_TARGET_HOST}:{TEST_TARGET_PORT}\r\n\r\n"
        )
        sock.sendall(connect_cmd.encode())
        response: bytes = b""
        while b"\r\n\r\n" not in response:
            chunk: bytes = sock.recv(4096)
            if not chunk:
                break
            response += chunk
        status_line: str = response.split(b"\r\n")[0].decode(errors="replace")
        elapsed: float = (time.monotonic() - start) * 1000

        if "200" in status_line:
            return {
                "success": True,
                "latency_ms": round(elapsed, 1),
                "message": f"代理连接成功, 延迟 {elapsed:.0f}ms",
            }
        return {
            "success": False,
            "latency_ms": round(elapsed, 1),
            "message": f"代理 CONNECT 被拒绝: {status_line}",
        }
    except OSError as exc:
        elapsed_fail: float = (time.monotonic() - start) * 1000
        return {
            "success": False,
            "latency_ms": round(elapsed_fail, 1),
            "message": f"代理通信失败: {exc}",
        }
    finally:
        with contextlib.suppress(OSError):
            sock.close()
