"""Embedded QQ engine: manages a NapCat Docker container (OneBot 11, real NTQQ).

NapCat 直接运行腾讯官方 QQ 客户端, 签名在客户端内部完成, 不依赖外部签名
服务器, 协议版本自动跟随 QQ。本模块负责按实例拉起/停止容器, 生成 OneBot
HTTP 配置, 并代理登录二维码。
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from hx_email.config import Settings

ENGINE_DIR_NAME: str = "qq-engines"
NAPCAT_IMAGE: str = "mlikiowa/napcat-docker:latest"
CONTAINER_PREFIX: str = "hx-messaging-"
QR_FILE_NAME: str = "qrcode.png"
_START_TIMEOUT_SECONDS: float = 90.0
_SUBDIRS: tuple[str, ...] = ("config", "data", "cache", "plugins")
# NapCat 的 stock entrypoint 启动 Xvfb 后只 sleep 2 秒就拉起 QQ, 存在竞态;
# 我们先用 -ac 起 Xvfb 并等 socket 就绪, 再 exec 官方 entrypoint。
_XVFB_WRAPPER: str = (
    "rm -f /tmp/.X1-lock; mkdir -p /tmp/.X11-unix; "
    "chown napcat:napcat /tmp/.X11-unix 2>/dev/null || true; "
    "(gosu napcat Xvfb :1 -screen 0 1080x760x16 -ac +extension GLX +render >/tmp/xvfb.log 2>&1 &); "
    "i=0; until [ -S /tmp/.X11-unix/X1 ] || [ $i -ge 60 ]; do sleep 1; i=$((i+1)); done; "
    "exec /app/entrypoint.sh"
)

_ENGINES: dict[int, QQEngineManager] = {}


def get_engine(instance_id: int) -> QQEngineManager | None:
    """Return the running embedded engine for an instance, if any."""
    return _ENGINES.get(instance_id)


def container_name(instance_id: int) -> str:
    return f"{CONTAINER_PREFIX}{instance_id}"


class QQEngineManager:
    """Per-instance lifecycle for the embedded NapCat (OneBot 11) engine."""

    def __init__(self, settings: Settings, instance_id: int) -> None:
        self._settings: Settings = settings
        self._instance_id: int = instance_id
        self._dir: Path = settings.data_dir.resolve() / ENGINE_DIR_NAME / str(instance_id)
        self._error: str = ""

    def _ensure_dirs(self) -> None:
        for name in _SUBDIRS:
            (self._dir / name).mkdir(parents=True, exist_ok=True)

    def _docker(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=120)

    def _container_running(self, name: str) -> bool:
        result: subprocess.CompletedProcess[str] = self._docker(
            "inspect", "-f", "{{.State.Running}}", name
        )
        return result.returncode == 0 and result.stdout.strip() == "true"

    def start(
        self,
        api_port: int = 3000,
        webui_port: int = 6099,
        event_url: str = "",
        access_token: str = "",
        download_url: str = "",
        sha256: str = "",
        proxy_url: str = "",
        sign_url: str = "",
    ) -> int:
        """Boot the NapCat container and wait until the login QR is ready."""
        self.stop()
        self._ensure_dirs()
        self._error = ""
        name: str = container_name(self._instance_id)

        # 拉取镜像(幂等)
        if not self._image_exists():
            pull: subprocess.CompletedProcess[str] = self._docker("pull", NAPCAT_IMAGE)
            if pull.returncode != 0:
                raise RuntimeError(
                    f"拉取 NapCat 镜像失败: {pull.stderr.strip() or pull.stdout.strip()}"
                )

        # 预写 OneBot HTTP 配置: HTTP 服务(容器内 3000, 发布到宿主随机端口)
        # + 事件回传(容器经 Docker 网桥网关访问宿主后端)
        gateway: str = self._bridge_gateway()
        if not event_url or event_url.startswith(("http://127.0.0.1", "http://localhost")):
            event_url = f"http://{gateway}:8000/api/v1/messaging/events/qq"
        onebot: dict[str, Any] = {
            "network": {
                "httpServers": [
                    {
                        "name": "hx-email",
                        "enable": True,
                        "host": "0.0.0.0",
                        "port": 3000,
                        "token": access_token,
                        "messagePostFormat": "array",
                        "debug": False,
                    }
                ],
                "httpClients": [
                    {
                        "name": "hx-email-events",
                        "enable": True,
                        "url": event_url,
                        "token": access_token,
                        "messagePostFormat": "array",
                        "debug": False,
                    }
                ],
                "httpSseServers": [],
                "websocketServers": [],
                "websocketClients": [],
                "plugins": [],
            }
        }
        (self._dir / "config" / "onebot11.json").write_text(
            json.dumps(onebot, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # WebUI 端口按实例随机(容器内, 不发布到宿主; 二维码走 cache 文件, 不需要 WebUI)
        (self._dir / "config" / "webui.json").write_text(
            json.dumps(
                {"host": "127.0.0.1", "port": webui_port, "token": access_token},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        env: list[str] = [f"NAPCAT_UID={os.getuid()}", f"NAPCAT_GID={os.getgid()}"]
        env_args: list[str] = []
        for item in env:
            env_args += ["-e", item]
        volumes: list[str] = []
        for sub in _SUBDIRS:
            target: str = "/app/.config/QQ" if sub == "data" else f"/app/napcat/{sub}"
            volumes += ["-v", f"{self._dir / sub}:{target}"]

        self._docker("rm", "-f", name)
        result: subprocess.CompletedProcess[str] = self._docker(
            "run",
            "-d",
            "--name",
            name,
            "-p",
            f"{api_port}:3000",
            *env_args,
            *volumes,
            "--entrypoint",
            "sh",
            NAPCAT_IMAGE,
            "-c",
            _XVFB_WRAPPER,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"NapCat 容器启动失败: {result.stderr.strip() or result.stdout.strip()}"
            )

        # 等二维码出现
        deadline: float = time.monotonic() + _START_TIMEOUT_SECONDS
        qr: Path = self._dir / "cache" / QR_FILE_NAME
        while time.monotonic() < deadline:
            if qr.is_file():
                break
            if not self._container_running(name):
                raise RuntimeError(f"NapCat 容器退出: {self._error or '请查看容器日志'}")
            time.sleep(1)
        else:
            raise RuntimeError("NapCat 启动超时(二维码未生成), 请检查容器日志")
        _ENGINES[self._instance_id] = self
        return self._instance_id + 10000

    def _bridge_gateway(self) -> str:
        """Return the Docker bridge gateway IP so the container can reach the backend."""
        result: subprocess.CompletedProcess[str] = self._docker(
            "network", "inspect", "bridge", "--format", "{{(index .IPAM.Config 0).Gateway}}"
        )
        gateway: str = result.stdout.strip()
        return gateway if gateway else "172.17.0.1"

    def _image_exists(self) -> bool:
        return self._docker("image", "inspect", NAPCAT_IMAGE).returncode == 0

    def qr_image(self, webui_port: int = 0) -> bytes | None:
        qr: Path = self._dir / "cache" / QR_FILE_NAME
        try:
            return qr.read_bytes() if qr.is_file() else None
        except OSError:
            return None

    def refresh_qr(self) -> None:
        """Restart the container to force a fresh login QR (manual refresh)."""
        name: str = container_name(self._instance_id)
        if not self._container_running(name):
            raise RuntimeError("QQ 引擎未运行, 请先启动内置引擎")
        result: subprocess.CompletedProcess[str] = self._docker("restart", name)
        if result.returncode != 0:
            raise RuntimeError(f"刷新二维码失败: {result.stderr.strip() or result.stdout.strip()}")
        deadline: float = time.monotonic() + _START_TIMEOUT_SECONDS
        qr: Path = self._dir / "cache" / QR_FILE_NAME
        while time.monotonic() < deadline:
            if qr.is_file():
                return
            time.sleep(1)
        raise RuntimeError("刷新二维码超时")

    def stop(self) -> None:
        _ENGINES.pop(self._instance_id, None)
        with suppress(Exception):
            self._docker("rm", "-f", container_name(self._instance_id))

    def is_running(self) -> bool:
        return self._container_running(container_name(self._instance_id))

    def logs(self, lines: int = 20) -> str:
        """Return the tail of the NapCat container log for diagnostics."""
        result: subprocess.CompletedProcess[str] = self._docker(
            "logs", "--tail", str(lines), container_name(self._instance_id)
        )
        return result.stdout.strip() or result.stderr.strip() or "(no logs)"
