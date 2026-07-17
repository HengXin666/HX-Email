#!/usr/bin/env bash
# PostToolUse: 仅对被编辑的 ts/tsx 文件跑 biome 单文件 format+lint。
# 设计为不阻断(exit 0): 真正的红线交给 Stop hook + lefthook pre-push。
set -uo pipefail

if ! command -v npx &>/dev/null; then
  exit 0
fi

if [[ -n "${CLAUDE_FILE_PATH:-}" ]]; then
  # 单文件快速模式
  file="$CLAUDE_FILE_PATH"
  ext="${file##*.}"
  [[ "$ext" = 'ts' || "$ext" = 'tsx' || "$ext" = 'js' || "$ext" = 'jsx' || "$ext" = 'json' ]] || exit 0
  npx @biomejs/biome check --write --no-errors-on-unmatched "$file" 2>/dev/null || true
else
  # 回退：全量（兼容旧版或非 Claude 环境）
  npx @biomejs/biome check --write --no-errors-on-unmatched ./src 2>/dev/null || true
fi
exit 0
