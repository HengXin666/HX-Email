"""gh CLI 是 GitHub 用户账号唯一的网络出口: 一次 ``<cli> api`` 调用就是一次 REST 或 GraphQL 请求.

本服务从不持有这个账号的 token. 用户在终端里对自己的包装脚本 (``GH_CONFIG_DIR=... exec gh``)
运行 ``auth login``, 这里只知道脚本的绝对路径. 为保证子进程只用包装脚本自己的凭据, 启动前清掉
``GH_TOKEN`` / ``GITHUB_TOKEN`` 一类变量, 以及名字里含 KEY, PASSWORD, SECRET, TOKEN 的全部变量.

返回值与 App 的 ``HttpTransport`` 同形 (``HttpResponse`` 或两种传输异常), 于是 App 的
``classify_response``, GraphQL 分类与写动作可以原样复用:

- ``CliTimeoutError``: 超时 (默认 90 秒), 请求可能已送达; 写入按 unknown 处理
- ``CliFailedError``: 非零退出且没有 HTTP 状态行, 无法判断是否送达, 同样按 unknown 处理
- ``CliMissingError``: 程序不存在或不可执行, 或明确的连接失败; 什么都没发出, 可以重试

内存: stdout 分块读取, 超过 4 MiB 立即杀掉子进程; stderr 只留前 16 KiB. 调用方按页请求,
一次只持有一页.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable, Coroutine, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Final

from hx_email.server.router.providers.impl.github.github_http import (
    GITHUB_API,
    HttpResponse,
    TransportConnectError,
    TransportTimeoutError,
)

HOSTNAME: Final[str] = "github.com"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 90.0
MAX_STDOUT_BYTES: Final[int] = 4 * 1024 * 1024
MAX_STDERR_BYTES: Final[int] = 16 * 1024
CHUNK_BYTES: Final[int] = 64 * 1024
STRIPPED_NAMES: Final[frozenset[str]] = frozenset(
    {"GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"}
    | {"GH_HOST", "GH_CONFIG_DIR"}
)
SECRET_PARTS: Final[tuple[str, ...]] = ("KEY", "PASSWORD", "SECRET", "TOKEN")
FIXED_ENV: Final[dict[str, str]] = {
    "GH_PROMPT_DISABLED": "1",
    "GH_NO_UPDATE_NOTIFIER": "1",
    "NO_COLOR": "1",
}
AUTH_HINTS: Final[tuple[str, ...]] = ("auth login", "not logged", "authentication")
CONNECT_HINTS: Final[tuple[str, ...]] = ("error connecting", "no such host", "connection refused")
BASE_HEADERS: Final[tuple[str, ...]] = (
    "Accept: application/vnd.github+json",
    "X-GitHub-Api-Version: 2022-11-28",
)


class CliTimeoutError(TransportTimeoutError):
    """The program did not finish in time; the request may have reached GitHub."""


class CliFailedError(TransportTimeoutError):
    """Non-zero exit without an HTTP status line: delivery cannot be ruled out."""


class CliMissingError(TransportConnectError):
    """The program could not be started, or failed before anything left the machine."""


@dataclass(frozen=True)
class CliOutput:
    returncode: int
    stdout: bytes
    stderr: str


# 子进程只用包装脚本自己的凭据: 清掉 GH_TOKEN 等以及名字含 KEY/PASSWORD/SECRET/TOKEN 的变量
# 决策记录: .agents/notes/implemented/feature/2026-11-09-github-cli-account.md
def clean_env(source: Mapping[str, str]) -> dict[str, str]:
    kept: dict[str, str] = {
        name: value
        for name, value in source.items()
        if name.upper() not in STRIPPED_NAMES
        and not any(part in name.upper() for part in SECRET_PARTS)
    }
    return kept | FIXED_ENV


async def read_capped(
    stream: asyncio.StreamReader | None, limit: int, on_overflow: Callable[[], None] | None
) -> bytes:
    """Read up to ``limit`` bytes; past it either stop the process or drain and discard."""
    if stream is None:
        return b""
    kept: bytearray = bytearray()
    while chunk := await stream.read(CHUNK_BYTES):
        if len(kept) + len(chunk) > limit:
            kept.extend(chunk[: max(0, limit - len(kept))])
            if on_overflow is not None:
                on_overflow()
                return bytes(kept)
            continue
        kept.extend(chunk)
    return bytes(kept)


async def run_cli(
    program: str,
    args: list[str],
    stdin_data: bytes | None,
    timeout: float,
    env: Mapping[str, str] | None = None,
) -> CliOutput:
    """Run ``program`` with a scrubbed environment and a hard timeout."""
    try:
        process = await asyncio.create_subprocess_exec(
            program,
            *args,
            stdin=asyncio.subprocess.PIPE if stdin_data is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=clean_env(os.environ if env is None else env),
        )
    except OSError as error:
        raise CliMissingError(f"{program} cannot be started: {error}") from error
    overflow: list[bool] = []

    def stop() -> None:
        overflow.append(True)
        process.kill()

    async def exchange() -> tuple[bytes, bytes, int]:
        if stdin_data is not None and process.stdin is not None:
            try:
                process.stdin.write(stdin_data)
                await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass
            process.stdin.close()
        out, err = await asyncio.gather(
            read_capped(process.stdout, MAX_STDOUT_BYTES, stop),
            read_capped(process.stderr, MAX_STDERR_BYTES, None),
        )
        return out, err, await process.wait()

    try:
        stdout, stderr, code = await asyncio.wait_for(exchange(), timeout)
    except TimeoutError as error:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise CliTimeoutError(f"{program} did not finish within {timeout:g}s") from error
    if overflow:
        raise CliFailedError(f"{program} printed more than {MAX_STDOUT_BYTES} bytes")
    return CliOutput(code, stdout, stderr.decode("utf-8", "replace"))


def endpoint_of(url: str) -> str | None:
    """``https://api.github.com/x`` or ``x`` to the ``gh api`` endpoint; other hosts are refused."""
    if url.startswith(GITHUB_API + "/"):
        return url[len(GITHUB_API) + 1 :]
    if "://" in url:
        return None
    return url.lstrip("/")


def split_include(raw: bytes) -> tuple[int, dict[str, str], bytes] | None:
    """Parse ``gh api --include`` output: status line, headers, blank line, body."""
    if not raw.startswith(b"HTTP/"):
        return None
    found: list[tuple[int, int]] = [
        (raw.find(sep), len(sep)) for sep in (b"\r\n\r\n", b"\n\r\n", b"\n\n") if sep in raw
    ]
    end, width = min(found) if found else (len(raw), 0)
    lines: list[str] = raw[:end].decode("utf-8", "replace").splitlines()
    parts: list[str] = lines[0].split()
    if len(parts) < 2 or not parts[1].isdigit():
        return None
    headers: dict[str, str] = {}
    for line in lines[1:]:
        name, sep, value = line.partition(":")
        if sep:
            headers[name.strip().lower()] = value.strip()
    return int(parts[1]), headers, raw[end + width :]


def decode_json(body: bytes) -> object:
    try:
        return json.loads(body) if body.strip() else {}
    except ValueError:
        return {}


def to_response(program: str, output: CliOutput) -> HttpResponse:
    parsed = split_include(output.stdout)
    if parsed is not None:
        status, headers, body = parsed
        return HttpResponse(status, headers, decode_json(body))
    if output.returncode == 0:
        return HttpResponse(200, {}, decode_json(output.stdout))
    detail: str = output.stderr.strip()[-500:] or f"exit code {output.returncode}"
    lowered: str = detail.lower()
    if any(hint in lowered for hint in AUTH_HINTS):
        return HttpResponse(401, {}, {"message": detail})
    if any(hint in lowered for hint in CONNECT_HINTS):
        raise CliMissingError(f"{program}: {detail}")
    raise CliFailedError(f"{program} failed: {detail}")


@dataclass(frozen=True)
class GhCli:
    """One wrapper script; ``env`` replaces ``os.environ`` as the source to scrub (tests)."""

    program: str
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    env: Mapping[str, str] | None = field(default=None, compare=False)

    async def api(
        self,
        method: str,
        url: str,
        body: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        endpoint: str | None = endpoint_of(url)
        if endpoint is None:
            return HttpResponse(422, {}, {"message": f"only {GITHUB_API} is supported: {url}"})
        args: list[str] = ["api", "--hostname", HOSTNAME, "--include", "--method", method]
        for line in (*BASE_HEADERS, *(f"{k}: {v}" for k, v in (headers or {}).items())):
            args += ["-H", line]
        args.append(endpoint)
        stdin_data: bytes | None = None
        if body is not None:
            args += ["--input", "-"]
            stdin_data = json.dumps(dict(body), ensure_ascii=False).encode("utf-8")
        output: CliOutput = await run_cli(self.program, args, stdin_data, self.timeout, self.env)
        return to_response(self.program, output)


def run_sync[T](coroutine: Coroutine[object, object, T]) -> T:
    """Run a coroutine from sync code (the dispatcher thread); never nest in a running loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coroutine).result()
