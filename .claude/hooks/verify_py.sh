#!/usr/bin/env bash
# Stop: Agent 准备结束时强制跑全量校验。
# 自动识别运行平台:
#   - CodeBuddy (CLAUDE_PROJECT_DIR/CODEBUDDY_PROJECT_DIR): exit 2 + stderr → 阻止结束并注入反馈
#   - Codex (无上述环境变量): JSON stdout + exit 0 → decision:block 阻止结束
set -uo pipefail

# 自动定位项目根目录并构建 scripts/verify.sh 路径
if [[ -n "${CODEBUDDY_PROJECT_DIR:-}" ]]; then
  PROJECT_DIR="${CODEBUDDY_PROJECT_DIR}"
elif [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
  PROJECT_DIR="${CLAUDE_PROJECT_DIR}"
else
  PROJECT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")"
fi

VERIFY_SCRIPT="${PROJECT_DIR}/scripts/verify.sh"

# 如果 verify.sh 不存在或 uv 不可用，直接放行
if [[ ! -f "$VERIFY_SCRIPT" ]]; then
  echo "[hooks] scripts/verify.sh 不存在，跳过校验" >&2
  exit 0
fi

if ! command -v uv &>/dev/null; then
  echo "[hooks] uv 未安装，跳过校验" >&2
  exit 0
fi

# 运行校验
cd "$PROJECT_DIR"
LOG_FILE="/tmp/cc_verify.log"

if bash "$VERIFY_SCRIPT" >"$LOG_FILE" 2>&1; then
  # 校验通过，放行
  exit 0
fi

# 校验未通过 — 生成失败内容
FAIL_MSG="校验未通过，请根据以下错误修复后再结束："
FAIL_DETAIL=$(cat "$LOG_FILE" 2>/dev/null || echo "无法读取日志")

# 判断运行平台
if [[ -n "${CODEBUDDY_PROJECT_DIR:-}" ]] || [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
  # CodeBuddy / Claude Code: exit 2 + stderr
  echo "$FAIL_MSG" >&2
  echo "$FAIL_DETAIL" >&2
  exit 2
fi

# Codex / OpenCode: exit 0 + JSON on stdout
# 需要对 JSON 内容做转义
REASON_JSON=$(echo "${FAIL_MSG}\n${FAIL_DETAIL}" | python3 -c "
import sys, json
text = sys.stdin.read().rstrip()
print(json.dumps(text))
" 2>/dev/null || echo '"校验未通过"')

cat <<JSONEOF
{"decision": "block", "reason": ${REASON_JSON}}
JSONEOF
exit 0
