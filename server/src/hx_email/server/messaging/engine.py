"""Embedded QQ protocol engine: downloads and manages a Lagrange.OneBot subprocess.

用户无需安装 NapCat/Lagrange;后端首次使用时自动下载引擎,生成配置,
拉起子进程,并把二维码通过后端接口代理给前端。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import time
import zipfile
from contextlib import suppress
from pathlib import Path
from typing import Any

import requests
from hx_email.config import Settings
from hx_email.server.messaging.impl.discovery import (
    ENGINE_DOWNLOAD_URL_ENV,
    ENGINE_URL_CACHE_NAME,
    read_cached_url,
    resolve_default_download_url,
    write_cached_url,
)

ENGINE_DIR_NAME: str = "qq-engines"
ENGINE_SHA256_ENV: str = "HX_EMAIL_QQ_ENGINE_SHA256"
DEFAULT_EXECUTABLE_NAME: str = "Lagrange.OneBot"
DEFAULT_ONEBOT_PORT: int = 3000
DEFAULT_WEBUI_PORT: int = 22000
START_TIMEOUT_SECONDS: float = 30.0
PROBE_TIMEOUT: float = 2.0
QR_PATH_CANDIDATES: tuple[str, ...] = (
    "/api/QRCode",
    "/api/qrcode",
    "/qrcode",
    "/qrcode.png",
    "/api/login/qrcode",
)
QR_FILE_NAME: str = "qr-0.png"
_PID_FILE_NAME: str = "engine.pid"


def pick_free_port() -> int:
    """Bind an ephemeral port and return its number (for engine endpoints)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def generate_lagrange_config(
    api_port: int,
    webui_port: int,
    event_url: str,
    access_token: str,
) -> dict[str, Any]:
    """Build a Lagrange.OneBot appsettings.json dict for headless operation."""
    return {
        "Logging": {"LogLevel": {"Default": "Information"}},
        "SignServerUrl": "https://sign.lagrangecore.org/api/sign",
        "Account": {"Uin": 0, "Password": ""},
        "Message": {"IgnoreSelf": True},
        "WebUi": {"Enable": True, "Port": webui_port, "UseHttps": False},
        "OneBot11": {
            "AccessToken": access_token,
            "Implementations": [
                {
                    "Type": "Http",
                    "Host": "127.0.0.1",
                    "Port": api_port,
                    "AccessToken": access_token,
                },
                {
                    "Type": "HttpPost",
                    "Host": "127.0.0.1",
                    "Port": pick_free_port(),
                    "PostUrls": [event_url],
                    "AccessToken": access_token,
                },
            ],
        },
    }


class QQEngineManager:
    """Per-instance lifecycle for the embedded Lagrange.OneBot engine."""

    def __init__(self, settings: Settings, instance_id: int) -> None:
        self._settings: Settings = settings
        self._dir: Path = settings.data_dir.resolve() / ENGINE_DIR_NAME / str(instance_id)
        self._process: subprocess.Popen[bytes] | None = None

    def ensure_installed(self, download_url: str = "", sha256: str = "") -> Path:
        """Download and extract the engine once; returns the executable path."""
        self._dir.mkdir(parents=True, exist_ok=True)
        executable: Path = self._dir / DEFAULT_EXECUTABLE_NAME
        if executable.exists():
            return executable
        cache_file: Path = self._dir.parent / ENGINE_URL_CACHE_NAME
        url: str = download_url or read_cached_url(cache_file) or resolve_default_download_url()
        archive: Path = self._dir / "engine.zip"
        try:
            with requests.get(url, stream=True, timeout=120) as response:
                response.raise_for_status()
                with archive.open("wb") as handle:
                    shutil.copyfileobj(response.raw, handle)
        except (requests.RequestException, OSError) as error:
            raise RuntimeError(
                f"QQ 引擎下载失败: {error}. 请检查网络, 或设置 "
                f"{ENGINE_DOWNLOAD_URL_ENV} 指定下载地址"
            ) from error
        expected: str = sha256 or os.environ.get(ENGINE_SHA256_ENV, "")
        if expected:
            digest: str = hashlib.sha256(archive.read_bytes()).hexdigest()
            if digest.lower() != expected.lower():
                raise RuntimeError("QQ 引擎下载校验失败, 请检查下载地址")
        try:
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(self._dir)
        except (zipfile.BadZipFile, OSError) as error:
            raise RuntimeError(f"QQ 引擎压缩包解析失败: {error}") from error
        archive.unlink(missing_ok=True)
        executable.chmod(0o755)
        write_cached_url(cache_file, url)
        return executable

    def start(
        self,
        api_port: int,
        webui_port: int,
        event_url: str,
        access_token: str,
        download_url: str = "",
        sha256: str = "",
    ) -> int:
        """Start the engine and wait until its OneBot HTTP API is ready."""
        executable: Path = self.ensure_installed(download_url, sha256)
        config: dict[str, Any] = generate_lagrange_config(
            api_port, webui_port, event_url, access_token
        )
        (self._dir / "appsettings.json").write_text(
            json.dumps(config, ensure_ascii=False, indent=2)
        )
        existing_pid: int | None = self._read_pid()
        if existing_pid is not None and self._alive(existing_pid):
            return existing_pid
        try:
            process: subprocess.Popen[bytes] = subprocess.Popen(
                [str(executable)],
                cwd=str(self._dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as error:
            raise RuntimeError(f"QQ 引擎进程启动失败: {error}") from error
        self._process = process
        self._write_pid(process.pid)
        deadline: float = time.monotonic() + START_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self._api_ready(api_port):
                return process.pid
            if process.poll() is not None:
                raise RuntimeError("QQ 引擎进程异常退出, 请检查引擎日志")
            time.sleep(0.5)
        raise RuntimeError("QQ 引擎启动超时, 请检查网络与下载地址")

    def stop(self) -> None:
        pid: int | None = self._read_pid()
        if pid is not None and self._alive(pid):
            with suppress(OSError):
                os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)
        self._pid_file().unlink(missing_ok=True)
        self._process = None

    def is_running(self) -> bool:
        pid: int | None = self._read_pid()
        return pid is not None and self._alive(pid)

    def qr_image(self, webui_port: int) -> bytes | None:
        """Fetch the QR image from the engine WebConsole via candidate endpoints."""
        if not self.is_running():
            return None
        base: str = f"http://127.0.0.1:{webui_port}"
        for path in QR_PATH_CANDIDATES:
            try:
                response: requests.Response = requests.get(base + path, timeout=PROBE_TIMEOUT)
            except requests.RequestException:
                continue
            if response.status_code == 200 and response.headers.get("content-type", "").startswith(
                "image/"
            ):
                return response.content
        qr_file: Path = self._dir / QR_FILE_NAME
        if qr_file.is_file():
            return qr_file.read_bytes()
        return None

    def _api_ready(self, api_port: int) -> bool:
        try:
            requests.post(
                f"http://127.0.0.1:{api_port}/get_status",
                json={},
                timeout=PROBE_TIMEOUT,
            )
            return True
        except requests.RequestException:
            return False

    def _pid_file(self) -> Path:
        return self._dir / _PID_FILE_NAME

    def _read_pid(self) -> int | None:
        try:
            return int(self._pid_file().read_text().strip())
        except (OSError, ValueError):
            return None

    def _write_pid(self, pid: int) -> None:
        self._pid_file().write_text(str(pid))

    @staticmethod
    def _alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
