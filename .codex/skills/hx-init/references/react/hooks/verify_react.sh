#!/usr/bin/env bash
# Stop: Agent 准备结束时跑前端校验。
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

cd "$PROJECT_DIR"
LOG_DIR="$(log_dir)"
mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${LOG_DIR}/react-verify-${STAMP}.log"
LATEST_LOG="${LOG_DIR}/react-verify-latest.log"
SUMMARY_FILE="${LOG_DIR}/react-verify-latest.summary.txt"
PASS=true
RAN=false

detect_pm() {
  if [[ -f "pnpm-lock.yaml" ]] && command -v pnpm &>/dev/null; then
    echo pnpm
  elif { [[ -f "bun.lockb" ]] || [[ -f "bun.lock" ]]; } && command -v bun &>/dev/null; then
    echo bun
  elif [[ -f "yarn.lock" ]] && command -v yarn &>/dev/null; then
    echo yarn
  elif command -v npm &>/dev/null; then
    echo npm
  else
    echo ""
  fi
}

has_script() {
  local script="$1"
  [[ -f "package.json" ]] || return 1
  node -e "const p=require('./package.json'); process.exit(p.scripts && p.scripts[process.argv[1]] ? 0 : 1)" "$script" 2>/dev/null
}

run_script() {
  local script="$1"
  local pm="$2"
  echo "==> package script: ${script}" >>"$LOG_FILE"
  RAN=true
  case "$pm" in
    pnpm) pnpm run "$script" >>"$LOG_FILE" 2>&1 ;;
    bun) bun run "$script" >>"$LOG_FILE" 2>&1 ;;
    yarn) yarn run "$script" >>"$LOG_FILE" 2>&1 ;;
    npm) npm run "$script" >>"$LOG_FILE" 2>&1 ;;
    *) return 127 ;;
  esac
}

run_bin() {
  local bin="$1"
  shift
  local pm="$1"
  shift
  echo "==> ${bin} $*" >>"$LOG_FILE"
  RAN=true
  if [[ -x "node_modules/.bin/${bin}" ]]; then
    "node_modules/.bin/${bin}" "$@" >>"$LOG_FILE" 2>&1
    return $?
  fi
  case "$pm" in
    pnpm) pnpm exec "$bin" "$@" >>"$LOG_FILE" 2>&1 ;;
    bun) bunx "$bin" "$@" >>"$LOG_FILE" 2>&1 ;;
    yarn) yarn exec "$bin" "$@" >>"$LOG_FILE" 2>&1 ;;
    npm) npx --no-install "$bin" "$@" >>"$LOG_FILE" 2>&1 ;;
    *) return 127 ;;
  esac
}

PM="$(detect_pm)"
: >"$LOG_FILE"

if [[ -z "$PM" ]]; then
  echo "[hooks] no supported JS package manager found; skip react verification" >&2
  exit 0
fi

if has_script lint; then
  run_script lint "$PM" || PASS=false
elif [[ -f "biome.json" || -f "biome.jsonc" ]]; then
  run_bin biome "$PM" ci || PASS=false
fi

if has_script typecheck; then
  run_script typecheck "$PM" || PASS=false
elif has_script "type-check"; then
  run_script "type-check" "$PM" || PASS=false
elif [[ -f "tsconfig.json" ]]; then
  run_bin tsc "$PM" --noEmit || PASS=false
fi

if [[ -f "knip.json" || -f "knip.ts" || -f ".knip.json" ]] || grep -q '"knip"' package.json 2>/dev/null; then
  run_bin knip "$PM" --no-progress || PASS=false
fi

if has_script test; then
  CI=1 run_script test "$PM" || PASS=false
fi

# 构建通常比 Stop hook 可接受的反馈时间更长，仅在显式启用时运行。
if [[ "${HX_VERIFY_BUILD:-0}" = "1" ]] && has_script build; then
  run_script build "$PM" || PASS=false
fi

if [[ "$RAN" = false ]]; then
  echo "[hooks] no react verification command detected; skip" >&2
  exit 0
fi

cp "$LOG_FILE" "$LATEST_LOG" 2>/dev/null || true

if [[ "$PASS" = true ]]; then
  exit 0
fi

if [[ -z "$PYTHON_BIN" ]]; then
  escaped_log="$(printf '%s' "$LATEST_LOG" | sed 's/\\/\\\\/g; s/"/\\"/g')"
  printf '{"decision":"block","reason":"React verification failed. Full log: %s"}\n' "$escaped_log"
  exit 0
fi

"$PYTHON_BIN" - "$LATEST_LOG" "$SUMMARY_FILE" <<'PY'
import json
import re
import sys
from pathlib import Path

log_path = Path(sys.argv[1])
summary_path = Path(sys.argv[2])
patterns = re.compile(r"(error|failed|failure|warning|unused|not found|cannot find|ts\d+)", re.I)
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

check_text = ", ".join(checks[:6]) if checks else "react verification"
detail_cmd = (
    f"sed -n '1,160p' {log_path}; "
    f"rg -n 'error|failed|warning|unused|TS[0-9]+' {log_path} | head -80"
)
sample_text = " | ".join(samples[:3])
reason = (
    f"React verification failed. checks={check_text}; matched_lines={matched}; "
    f"total_log_lines={total}; log={log_path}; details: {detail_cmd}"
)
if sample_text:
    reason = f"{reason}; samples: {sample_text}"

summary = [
    "React verification failed",
    f"checks: {check_text}",
    f"matched lines: {matched}",
    f"total log lines: {total}",
    f"log: {log_path}",
    "detail commands:",
    f"  sed -n '1,160p' {log_path}",
    f"  rg -n 'error|failed|warning|unused|TS[0-9]+' {log_path} | head -80",
    "samples:",
]
summary.extend(f"  {s}" for s in samples)
summary_path.write_text("\n".join(summary) + "\n", encoding="utf-8")

print(json.dumps({
    "decision": "block",
    "reason": reason[:1800],
    "systemMessage": f"React verification failed; summary={summary_path}; log={log_path}",
}, ensure_ascii=False))
PY
exit 0
