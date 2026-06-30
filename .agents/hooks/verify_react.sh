#!/usr/bin/env bash
# Stop: Agent 准备结束时强制全量校验。
# Web: biome ci + tsc --noEmit + knip
# 自动识别平台：CodeBuddy(exit 2+stderr) vs Codex(JSON+exit 0)
set -uo pipefail

if [[ -n "${CODEBUDDY_PROJECT_DIR:-}" ]]; then
  PROJECT_DIR="${CODEBUDDY_PROJECT_DIR}"
elif [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
  PROJECT_DIR="${CLAUDE_PROJECT_DIR}"
else
  PROJECT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")"
fi

cd "$PROJECT_DIR"
LOG_FILE="/tmp/web_verify.log"
PASS=true

# 1. biome ci
if command -v npx &>/dev/null; then
  echo "==> biome ci" >"$LOG_FILE"
  npx @biomejs/biome ci 2>>"$LOG_FILE" >>"$LOG_FILE" || PASS=false
fi

# 2. tsc 类型检查
if [[ -f "tsconfig.json" ]] && command -v npx &>/dev/null; then
  echo "==> tsc --noEmit" >>"$LOG_FILE"
  npx tsc --noEmit 2>>"$LOG_FILE" >>"$LOG_FILE" || PASS=false
fi

# 3. knip 死代码检测
if command -v npx &>/dev/null && npx knip --version &>/dev/null 2>&1; then
  echo "==> knip" >>"$LOG_FILE"
  npx knip --no-progress 2>>"$LOG_FILE" >>"$LOG_FILE" || PASS=false
fi

if $PASS; then
  exit 0
fi

FAIL_MSG="校验未通过，请根据以下错误修复后再结束："
FAIL_DETAIL=$(cat "$LOG_FILE" 2>/dev/null || echo "无法读取日志")

if [[ -n "${CODEBUDDY_PROJECT_DIR:-}" ]] || [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
  echo "$FAIL_MSG" >&2
  echo "$FAIL_DETAIL" >&2
  exit 2
fi

REASON_JSON=$(echo "${FAIL_MSG}\n${FAIL_DETAIL}" | python3 -c "
import sys, json
text = sys.stdin.read().rstrip()
print(json.dumps(text))
" 2>/dev/null || echo '"校验未通过"')

cat <<JSONEOF
{"decision": "block", "reason": ${REASON_JSON}}
JSONEOF
exit 0
