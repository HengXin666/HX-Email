#!/usr/bin/env bash
# Stop: Agent 准备结束时跑校验。
# 失败时只输出精简 JSON 摘要; 完整日志写入 .git/hx-init/logs 或用户 cache。
set -uo pipefail
HOOK_INPUT="$(cat || true)"
PYTHON_BIN="$(command -v python3 || command -v python || true)"

is_stop_hook_active() {
  if [[ -z "$PYTHON_BIN" ]]; then
    grep -qE '"stop_hook_active"[[:space:]]*:[[:space:]]*true' <<<"$HOOK_INPUT"
    return $?
  fi
  HOOK_INPUT="$HOOK_INPUT" "$PYTHON_BIN" - <<'PY'
import json
import os
import sys

try:
    data = json.loads(os.environ.get("HOOK_INPUT", "") or "{}")
except json.JSONDecodeError:
    data = {}

sys.exit(0 if data.get("stop_hook_active") is True else 1)
PY
}

if [[ -n "${CODEBUDDY_PROJECT_DIR:-}" ]]; then
  PROJECT_DIR="${CODEBUDDY_PROJECT_DIR}"
elif [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
  PROJECT_DIR="${CLAUDE_PROJECT_DIR}"
else
  PROJECT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")"
fi

if is_stop_hook_active; then
  exit 0
fi

log_dir() {
  if git -C "$PROJECT_DIR" rev-parse --git-dir >/dev/null 2>&1; then
    local git_path
    git_path="$(git -C "$PROJECT_DIR" rev-parse --git-path hx-init/logs)"
    case "$git_path" in
      /*) echo "$git_path" ;;
      *) echo "$PROJECT_DIR/$git_path" ;;
    esac
  else
    local key
    key="$(printf '%s' "$PROJECT_DIR" | cksum | awk '{print $1}')"
    echo "${XDG_CACHE_HOME:-$HOME/.cache}/hx-init/logs/${key}"
  fi
}

VERIFY_SCRIPT="${PROJECT_DIR}/scripts/verify.sh"
LOG_DIR="$(log_dir)"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/project-verify-${STAMP}.log"
LATEST_LOG="${LOG_DIR}/project-verify-latest.log"
SUMMARY_FILE="${LOG_DIR}/project-verify-latest.summary.txt"

if [[ ! -f "$VERIFY_SCRIPT" ]]; then
  echo "[hooks] scripts/verify.sh missing; skip project verification" >&2
  exit 0
fi

cd "$PROJECT_DIR"

if bash "$VERIFY_SCRIPT" >"$LOG_FILE" 2>&1; then
  cp "$LOG_FILE" "$LATEST_LOG" 2>/dev/null || true
  exit 0
fi

cp "$LOG_FILE" "$LATEST_LOG" 2>/dev/null || true

if [[ -z "$PYTHON_BIN" ]]; then
  escaped_log="$(printf '%s' "$LATEST_LOG" | sed 's/\\/\\\\/g; s/"/\\"/g')"
  printf '{"decision":"block","reason":"Project verification failed. Full log: %s"}\n' "$escaped_log"
  exit 0
fi

"$PYTHON_BIN" - "$LATEST_LOG" "$SUMMARY_FILE" <<'PY'
import json
import re
import sys
from pathlib import Path

log_path = Path(sys.argv[1])
summary_path = Path(sys.argv[2])
patterns = re.compile(r"(error|failed|failure|traceback|warning|unused|invalid)", re.I)
checks = []
samples = []
matched = 0
total = 0
max_samples = 5

try:
    with log_path.open(encoding="utf-8", errors="replace") as f:
        for raw in f:
            total += 1
            line = raw.strip()
            if line.startswith("==>"):
                checks.append(line.replace("==>", "").strip())
            if patterns.search(line):
                matched += 1
                if len(samples) < max_samples:
                    samples.append(line[:220])
except OSError:
    pass

check_text = ", ".join(checks[:6]) if checks else "scripts/verify.sh"
detail_cmd = (
    f"sed -n '1,160p' {log_path}; "
    f"rg -n 'error|failed|Traceback|warning|unused' {log_path} | head -80"
)
sample_text = " | ".join(samples[:3])
reason = (
    f"Project verification failed. checks={check_text}; matched_lines={matched}; "
    f"total_log_lines={total}; log={log_path}; details: {detail_cmd}"
)
if sample_text:
    reason = f"{reason}; samples: {sample_text}"

summary = [
    "Project verification failed",
    f"checks: {check_text}",
    f"matched lines: {matched}",
    f"total log lines: {total}",
    f"log: {log_path}",
    "detail commands:",
    f"  sed -n '1,160p' {log_path}",
    f"  rg -n 'error|failed|Traceback|warning|unused' {log_path} | head -80",
    "samples:",
]
summary.extend(f"  {s}" for s in samples)
summary_path.write_text("\n".join(summary) + "\n", encoding="utf-8")

print(json.dumps({
    "decision": "block",
    "reason": reason[:1800],
    "systemMessage": f"Project verification failed; summary={summary_path}; log={log_path}",
}, ensure_ascii=False))
PY
exit 0
