"""Docker self-update runner.

The backend runs inside a compose-managed container. To update itself it
launches a *detached helper container* through the mounted host docker socket:

1. resolve this container's id and image (``docker inspect``),
2. run ``docker run -d --volumes-from <self> <our-image>`` which mounts the
   same volumes (docker socket, compose dir, data dir) onto the helper,
3. the helper executes ``docker compose pull`` + ``docker compose up -d``,
   so the update keeps running even after this container is recreated.
"""

import json
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from hx_email.config import Settings

HELPER_NAME_PREFIX: str = "hx-email-self-update"
STATUS_FILE_NAME: str = "self_update_status.json"
COMPOSE_DIR: str = "/compose"


@dataclass(frozen=True)
class DockerConfig:
    enabled: bool
    compose_dir: str
    compose_file: str
    image: str
    timeout_seconds: int


@dataclass(frozen=True)
class UpdateOutcome:
    success: bool
    message: str
    output: str


def resolve_config(settings: Settings) -> DockerConfig:
    """Build the update config from application settings."""
    default_file = (
        "docker-compose.yml"
        if Path(settings.update_compose_dir, "docker-compose.yml").exists()
        else "docker-compose.bridge.yml"
    )
    return DockerConfig(
        enabled=settings.update_enabled,
        compose_dir=settings.update_compose_dir,
        compose_file=settings.update_compose_file or default_file,
        image=settings.update_image,
        timeout_seconds=settings.update_timeout_seconds,
    )


class DockerRunner:
    """Runs the compose-based self-update via a detached helper container."""

    def __init__(self, config: DockerConfig) -> None:
        self._config = config

    def availability_reason(self) -> str:
        """Return an empty string when self-update can run, else a reason."""
        if not self._config.enabled:
            return (
                "自动更新未启用, 请在 .env 设置 HX_EMAIL_UPDATE_ENABLED=true "
                "并使用新版 docker-compose 部署"
            )
        if shutil.which("docker") is None:
            return "容器内未安装 docker CLI, 无法自动更新"
        mounts = self._inspect_mounts()
        if mounts is None:
            return "无法连接宿主机 Docker, 请确认已挂载 /var/run/docker.sock"
        if COMPOSE_DIR not in mounts:
            return "未检测到 /compose 挂载, 请使用新版 docker-compose 文件重新部署"
        return ""

    def run_update(self, target_version: str) -> UpdateOutcome:
        """Launch the detached helper, wait for it, and return its outcome."""
        reason = self.availability_reason()
        if reason:
            raise RuntimeError(reason)
        image = self._resolve_image()
        if not image:
            raise RuntimeError("无法确定当前镜像名 (缺少 HX_EMAIL_UPDATE_IMAGE)")
        helper_name = f"{HELPER_NAME_PREFIX}-{int(time.time())}"
        self._cleanup_stale_helpers()
        launch = self._run_command(
            [
                "docker",
                "run",
                "-d",
                "--name",
                helper_name,
                "--volumes-from",
                socket.gethostname(),
                "-w",
                COMPOSE_DIR,
                "--entrypoint",
                "/bin/sh",
                image,
                "-c",
                self._helper_script(target_version),
            ],
            timeout=self._config.timeout_seconds,
        )
        if launch.returncode != 0:
            raise RuntimeError(f"启动更新容器失败: {(launch.stderr or launch.stdout).strip()}")
        helper_id: str = launch.stdout.strip()
        wait = self._run_command(
            ["docker", "wait", helper_id], timeout=self._config.timeout_seconds
        )
        logs = self._run_command(["docker", "logs", helper_id], timeout=30)
        self._run_command(["docker", "rm", "-f", helper_id], timeout=30)
        output: str = (logs.stdout or "") + (logs.stderr or "")
        exit_code = int(wait.stdout.strip()) if wait.returncode == 0 and wait.stdout.strip() else -1
        if exit_code == 0:
            return UpdateOutcome(success=True, message="更新完成, 新版本已启动", output=output)
        return UpdateOutcome(success=False, message=f"更新失败(exit {exit_code})", output=output)

    def _resolve_image(self) -> str:
        probe = self._run_command(
            [
                "docker",
                "inspect",
                "--format",
                "{{.Config.Image}}",
                socket.gethostname(),
            ],
            timeout=15,
        )
        if probe.returncode == 0 and probe.stdout.strip():
            return probe.stdout.strip()
        return self._config.image

    def _inspect_mounts(self) -> str | None:
        probe = self._run_command(
            [
                "docker",
                "inspect",
                "--format",
                "{{range .Mounts}}{{.Destination}} {{end}}",
                socket.gethostname(),
            ],
            timeout=15,
        )
        if probe.returncode != 0:
            return None
        return probe.stdout

    def _cleanup_stale_helpers(self) -> None:
        listing = self._run_command(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                f"name={HELPER_NAME_PREFIX}-",
                "--filter",
                "status=exited",
            ],
            timeout=15,
        )
        for container_id in listing.stdout.split():
            self._run_command(["docker", "rm", "-f", container_id], timeout=15)

    def _helper_script(self, target_version: str) -> str:
        compose_file = f"{COMPOSE_DIR}/{self._config.compose_file}"
        status_json = json.dumps(
            {
                "success": True,
                "version": target_version,
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            ensure_ascii=False,
        )
        return (
            "set -e; "
            f"docker compose -f {compose_file} --project-directory {COMPOSE_DIR} pull && "
            f"docker compose -f {compose_file} --project-directory {COMPOSE_DIR} "
            "up -d --remove-orphans && "
            f"printf '%s' '{status_json}' > /data/{STATUS_FILE_NAME}"
        )

    def _run_command(self, args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
