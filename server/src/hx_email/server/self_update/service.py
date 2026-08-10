"""Self-update service: orchestrate check/apply/status for docker deployments."""

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from hx_email.server.self_update.docker import (
    STATUS_FILE_NAME,
    DockerConfig,
    DockerRunner,
    UpdateOutcome,
)


@dataclass
class UpdateState:
    running: bool = False
    phase: str = ""
    success: bool | None = None
    message: str = ""
    output: str = ""
    target_version: str = ""
    started_at: str = ""
    finished_at: str = ""


class SelfUpdateService:
    """Holds the single-flight update state and runs updates in the background."""

    def __init__(
        self,
        config: DockerConfig,
        data_dir: Path,
        runner: DockerRunner | None = None,
    ) -> None:
        self._config = config
        self._runner = runner if runner is not None else DockerRunner(config)
        self._status_file = data_dir / STATUS_FILE_NAME
        self._lock = threading.Lock()
        self._state = UpdateState()

    def status(self) -> dict[str, object]:
        """Return the current availability and run state of self-update."""
        with self._lock:
            state = self._state
        reason: str = self._runner.availability_reason()
        return {
            "enabled": self._config.enabled,
            "available": reason == "",
            "available_reason": reason,
            "running": state.running,
            "phase": state.phase,
            "success": state.success,
            "message": state.message,
            "output": state.output[-2000:],
            "target_version": state.target_version,
            "started_at": state.started_at,
            "finished_at": state.finished_at,
            "last_update": self._read_last_update(),
        }

    def apply(self, target_version: str) -> dict[str, object]:
        """Start an update in the background; raise RuntimeError if unavailable."""
        reason: str = self._runner.availability_reason()
        if reason:
            raise RuntimeError(reason)
        with self._lock:
            if self._state.running:
                return self.status()
            self._state = UpdateState(
                running=True,
                phase="启动更新容器",
                target_version=target_version,
                started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            )
        thread = threading.Thread(target=self._run, args=(target_version,), daemon=True)
        thread.start()
        return self.status()

    def _run(self, target_version: str) -> None:
        try:
            outcome: UpdateOutcome = self._runner.run_update(target_version)
            self._finish(outcome.success, outcome.message, outcome.output)
        except Exception as error:
            self._finish(False, f"更新失败: {error}", "")

    def _finish(self, success: bool, message: str, output: str) -> None:
        with self._lock:
            self._state.running = False
            self._state.phase = "done" if success else "failed"
            self._state.success = success
            self._state.message = message
            self._state.output = output
            self._state.finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _read_last_update(self) -> dict[str, object]:
        try:
            parsed: object = json.loads(self._status_file.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                return parsed
            return {}
        except (OSError, json.JSONDecodeError):
            return {}
