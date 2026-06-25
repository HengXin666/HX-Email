#!/usr/bin/env bash
# Stop: Agent 准备结束时强制跑全量校验。
# 退出码约定 (Claude Code): exit 2 = 阻止结束, stderr 内容回灌给 Agent 让其自修。
set -uo pipefail
ROOT_DIR="${CLAUDE_PROJECT_DIR}"
cd "${ROOT_DIR}"
if bash "${ROOT_DIR}/scripts/verify.sh" >/tmp/cc_verify.log 2>&1; then
  exit 0
fi
echo "校验未通过, 请根据以下错误修复后再结束:" >&2
cat /tmp/cc_verify.log >&2
exit 2
