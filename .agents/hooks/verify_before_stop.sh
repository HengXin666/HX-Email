#!/usr/bin/env bash
# Stop: Agent 准备结束时强制跑全量校验。
# 退出码约定: exit 2 = 阻止/续写结束, stderr 内容回灌给 Agent 让其自修。
set -uo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="${CODEBUDDY_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-$(cd "${script_dir}/../.." && pwd)}}"
cd "${project_dir}"
if bash scripts/verify.sh >/tmp/cc_verify.log 2>&1; then
  exit 0
fi
fail_msg="校验未通过, 请根据以下错误修复后再结束:"
if [[ -n "${CODEBUDDY_PROJECT_DIR:-}" ]] || [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
  echo "${fail_msg}" >&2
  cat /tmp/cc_verify.log >&2
  exit 2
fi
reason_json=$(python3 -c 'import json, pathlib; print(json.dumps("校验未通过, 请根据以下错误修复后再结束:\n" + pathlib.Path("/tmp/cc_verify.log").read_text()))')
printf '{"decision":"block","reason":%s}\n' "${reason_json}"
exit 0
