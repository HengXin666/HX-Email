"""Helpers for MCP tests: session-aware JSON-RPC calls and a raw ASGI SSE reader.

Starlette's TestClient buffers a whole response, so an endless SSE stream is read by
driving the ASGI app directly: ``read_stream`` collects body chunks, runs ``act`` in a
worker thread once the stream is open, and sends ``http.disconnect`` as soon as
``until`` accepts the text received so far.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import anyio
from fastapi.testclient import TestClient


def initialize(client: TestClient, headers: dict[str, str]) -> dict[str, str]:
    reply = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        },
        headers=headers,
    )
    assert reply.status_code == 200, reply.text
    return {**headers, "Mcp-Session-Id": reply.headers["Mcp-Session-Id"]}


def rpc(
    client: TestClient, headers: dict[str, str], method: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        body["params"] = params
    return client.post("/mcp", json=body, headers=headers).json()  # type: ignore[no-any-return]


def tool(
    client: TestClient, headers: dict[str, str], name: str, **arguments: Any
) -> dict[str, Any]:
    return rpc(client, headers, "tools/call", {"name": name, "arguments": arguments})


def validate(schema: dict[str, Any], value: Any, path: str = "$") -> None:
    """The JSON Schema subset the output schemas use: type, properties, required, items."""
    kinds: dict[str, Any] = {
        "object": dict,
        "array": list,
        "string": str,
        "boolean": bool,
        "integer": int,
        "number": (int, float),
    }
    expected = schema.get("type")
    if expected is not None:
        assert isinstance(value, kinds[expected]), f"{path}: {value!r} is not {expected}"
        if expected == "integer":
            assert not isinstance(value, bool), f"{path}: bool is not integer"
    for key in schema.get("required", []):
        assert key in value, f"{path}: missing {key}"
    for key, sub in schema.get("properties", {}).items():
        if isinstance(value, dict) and key in value:
            validate(sub, value[key], f"{path}.{key}")
    if "items" in schema and isinstance(value, list):
        for index, item in enumerate(value):
            validate(schema["items"], item, f"{path}[{index}]")


async def read_stream_async(
    app: Any,
    headers: dict[str, str],
    until: Callable[[str], bool],
    act: Callable[[], None] | None,
    timeout: float,
) -> tuple[int, dict[str, str], str]:
    chunks: list[str] = []
    meta: dict[str, Any] = {"status": 0, "headers": {}}
    gone = anyio.Event()
    acted: list[bool] = []

    async def receive() -> dict[str, Any]:
        await gone.wait()
        return {"type": "http.disconnect"}

    async def run_act() -> None:
        if act is not None:
            await anyio.to_thread.run_sync(act)

    async with anyio.create_task_group() as group:

        async def send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                meta["status"] = message["status"]
                meta["headers"] = {k.decode().lower(): v.decode() for k, v in message["headers"]}
                if meta["status"] != 200:
                    gone.set()
                return
            chunks.append(message.get("body", b"").decode())
            text: str = "".join(chunks)
            if not acted and "stream open" in text:
                acted.append(True)
                group.start_soon(run_act)
            if until(text):
                gone.set()

        scope: dict[str, Any] = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/mcp",
            "raw_path": b"/mcp",
            "query_string": b"",
            "root_path": "",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
        with anyio.fail_after(timeout):
            await app(scope, receive, send)
    return int(meta["status"]), dict(meta["headers"]), "".join(chunks)


def read_stream(
    client: TestClient,
    headers: dict[str, str],
    until: Callable[[str], bool],
    act: Callable[[], None] | None = None,
    timeout: float = 10.0,
) -> tuple[int, dict[str, str], str]:
    return anyio.run(read_stream_async, client.app, headers, until, act, timeout)
