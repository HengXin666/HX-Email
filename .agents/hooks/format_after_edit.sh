#!/usr/bin/env bash
# PostToolUse: Agent 每次写/改文件后自动跑, 顺手格式化 + 修简单问题。
# 设计为"不阻断"(exit 0): 格式化是辅助, 真正的红线交给 Stop hook。
set -uo pipefail
uv run ruff format . >/dev/null 2>&1 || true
uv run ruff check --fix . >/dev/null 2>&1 || true
exit 0
