#!/usr/bin/env bash
# 验证闭环 (uv 版): 给 Agent 明确 pass/fail 信号. Stop hook 复用本脚本.
set -euo pipefail
echo "==> [1/7] ruff check (含 PLC2401 中文命名拦截)"
uv run ruff check .
echo "==> [2/7] ruff format --check"
uv run ruff format --check .
echo "==> [3/7] type-check (mypy)"
(cd server && uv run mypy .)
echo "==> [4/7] arch-check (300行/文件数/_前缀/中文命名)"
uv run python scripts/check_arch.py server
echo "==> [5/7] react format/lint (biome)"
(cd web && npx @biomejs/biome check . --no-errors-on-unmatched)
echo "==> [6/7] react type-check (tsc)"
(cd web && npx tsc -b --pretty false)
echo "==> [7/7] react dead-code (knip)"
(cd web && npx knip --no-progress)
echo "ALL PASS"
